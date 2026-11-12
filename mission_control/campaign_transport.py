"""Fixed Meta Page operations. No redirects, arbitrary routes or mutation retries."""

import http.client
import json
import re
import time
from urllib.parse import urlencode, urlsplit, parse_qs
from .aeo_transport import address, PinnedHTTPS, response_headers, response_body
from .aeo_tls import trust_context
from .common import Invalid, digest
from .payment_signature import strict_json
from .social_auth import app_secret_proof
from .social_contract import opaque
from .social_registry import META_VERSION
from .campaign_contract import numeric


class Unconfirmed(Invalid):
    """A provider operation may have happened; never retry a mutation blindly."""


def post_id(value, page_id):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,40}_[0-9]{1,40}", value):
        raise Unconfirmed("Provider returned an unconfirmed post identity")
    if value.split("_", 1)[0] != page_id:
        raise Unconfirmed("Provider returned a post outside the selected Page")
    return value


def attachment_destination(value):
    """Decode only the official link wrapper without making another request."""
    if not isinstance(value, str) or not 1 <= len(value) <= 8192:
        raise Unconfirmed("Post link destination was not confirmed")
    try:
        parts = urlsplit(value)
    except ValueError:
        raise Unconfirmed("Post link destination was not confirmed") from None
    if parts.hostname != "l.facebook.com":
        return value
    if parts.scheme != "https" or parts.netloc != "l.facebook.com" or parts.path != "/l.php" or parts.fragment:
        raise Unconfirmed("Post link redirect was not confirmed")
    try:
        destinations = parse_qs(parts.query, max_num_fields=10, strict_parsing=True).get("u", [])
    except ValueError:
        raise Unconfirmed("Post link destination was not confirmed") from None
    if len(destinations) != 1:
        raise Unconfirmed("Post link destination was ambiguous")
    return destinations[0]


def post_attachment_link(attachments):
    """Require one unambiguous link attachment or an explicitly empty list."""
    if not isinstance(attachments, dict) or not isinstance(attachments.get("data"), list):
        raise Unconfirmed("Post attachment readback was not confirmed")
    rows = attachments["data"]
    if not rows:
        return None
    if len(rows) != 1 or not isinstance(rows[0], dict) or "subattachments" in rows[0]:
        raise Unconfirmed("Post attachment readback was ambiguous")
    row = rows[0]
    target = row.get("target")
    if not isinstance(target, dict):
        raise Unconfirmed("Post link destination was not confirmed")
    observed = attachment_destination(target.get("url"))
    if "url" in row and attachment_destination(row["url"]) != observed:
        raise Unconfirmed("Post link readback was ambiguous")
    return observed


def check_post_content(value, content_hash):
    message = value.get("message")
    link = value.get("link")
    if "attachments" in value:
        observed = post_attachment_link(value["attachments"])
        if link is not None and link != observed:
            raise Unconfirmed("Post link readback was ambiguous")
        link = observed
    if not isinstance(message, str) or (link is not None and not isinstance(link, str)):
        raise Unconfirmed("Post content readback was not confirmed")
    if digest({"message": message, "link": link}) != content_hash:
        raise Unconfirmed("Post content differs from its approved hash")


def checked_permalink(permalink):
    if permalink is None:
        return None
    try:
        parts = urlsplit(permalink) if isinstance(permalink, str) and len(permalink) <= 2048 else None
    except ValueError:
        raise Unconfirmed("Post permalink readback was invalid") from None
    if (
        not parts
        or parts.scheme != "https"
        or parts.hostname not in ("www.facebook.com", "facebook.com")
        or parts.username
        or parts.password
    ):
        raise Unconfirmed("Post permalink readback was invalid")
    return permalink


def paid_values(kind, fields):
    if kind == "campaign" and (fields["objective"] != "OUTCOME_ENGAGEMENT" or fields["special_ad_categories"] != []):
        raise Invalid("Unsupported campaign objective or special category")
    if kind == "campaign" and fields["is_adset_budget_sharing_enabled"] is not False:
        raise Invalid("Ad set budget sharing must remain disabled")
    if kind == "adset" and (
        fields["billing_event"] != "IMPRESSIONS" or fields["optimization_goal"] != "POST_ENGAGEMENT"
    ):
        raise Invalid("Unsupported advertising optimization")


def paid_shape(kind, fields):
    expected = {
        "campaign": {"name", "objective", "status", "special_ad_categories", "is_adset_budget_sharing_enabled"},
        "adset": {
            "name",
            "campaign_id",
            "lifetime_budget",
            "end_time",
            "billing_event",
            "optimization_goal",
            "targeting",
            "status",
        },
        "creative": {"name", "object_story_id"},
        "ad": {"name", "adset_id", "creative", "status"},
    }
    edges = {"campaign": "campaigns", "adset": "adsets", "creative": "adcreatives", "ad": "ads"}
    if kind not in expected or set(fields) != expected[kind]:
        raise Invalid("Unsupported advertising construction")
    if kind != "creative" and fields["status"] != "PAUSED":
        raise Invalid("New advertising objects must start paused")
    paid_values(kind, fields)
    return edges[kind]


class MetaTransport:
    def request(self, method, route, fields, token, alive):
        """One request to the pinned Graph host; no raw response is exposed on errors."""
        token = opaque(token, "access token")
        deadline = time.monotonic() + 30
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Cache-Control": "no-store",
            "Authorization": "Bearer " + token,
        }
        body = None
        if method == "GET":
            route += "?" + urlencode(fields)
        else:
            body = urlencode(fields).encode("ascii")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if body and len(body) > 32768:
            raise Invalid("Campaign request exceeds the supported size")
        conn = None
        alive()
        try:
            conn = PinnedHTTPS("graph.facebook.com", address("graph.facebook.com", deadline), trust_context(), deadline)
            conn.request(method, route, body=body, headers=headers)
            response = conn.getresponse()
            if response.status not in (200, 201):
                raise Unconfirmed("Provider operation was not confirmed")
            raw = response_body(response, response_headers(response), 1048576, conn, deadline)
            data = strict_json(raw)
            if not isinstance(data, dict) or data.get("error"):
                raise Unconfirmed("Provider response was not confirmed")
            return data
        except Unconfirmed:
            raise
        except (OSError, ValueError, TimeoutError, RecursionError, http.client.HTTPException, Invalid):
            raise Unconfirmed("Provider operation was not confirmed") from None
        finally:
            if conn is not None:
                conn.close()

    def publish(self, page_id, message, link, page_token, secret, alive):
        numeric(page_id)
        fields = {"message": message, "appsecret_proof": app_secret_proof(page_token, secret)}
        if link is not None:
            fields["link"] = link
        value = self.request("POST", "/" + META_VERSION + "/" + page_id + "/feed", fields, page_token, alive)
        return post_id(value.get("id"), page_id)

    def read_post(self, page_id, identity, content_hash, page_token, secret, alive):
        post_id(identity, page_id)
        fields = {
            "fields": "id,message,permalink_url,from,attachments{url,target}",
            "appsecret_proof": app_secret_proof(page_token, secret),
        }
        value = self.request("GET", "/" + META_VERSION + "/" + identity, fields, page_token, alive)
        if value.get("id") != identity:
            raise Unconfirmed("Exact post readback was not confirmed")
        source = value.get("from")
        if not isinstance(source, dict) or source.get("id") != page_id:
            raise Unconfirmed("Post Page readback was not confirmed")
        check_post_content(value, content_hash)
        permalink = checked_permalink(value.get("permalink_url"))
        return {"id": identity, "permalink_url": permalink}

    def ad_account(self, account_id, token, secret, alive):
        numeric(account_id)
        fields = {
            "fields": "id,account_status,currency,funding_source",
            "appsecret_proof": app_secret_proof(token, secret),
        }
        data = self.request("GET", "/" + META_VERSION + "/act_" + account_id, fields, token, alive)
        if data.get("id") != "act_" + account_id or data.get("account_status") != 1:
            raise Unconfirmed("Selected advertising account is not confirmed active")
        if not isinstance(data.get("funding_source"), str) or not data["funding_source"]:
            raise Unconfirmed("Advertising account funding is not confirmed")
        return {"id": data["id"], "currency": data.get("currency"), "account_status": data["account_status"]}

    def create_paid(self, kind, account_id, fields, token, secret, alive):
        """Only the four fixed typed construction steps can reach a provider edge."""
        numeric(account_id)
        edge = paid_shape(kind, fields)
        data = {
            key: json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list, bool)) else str(value)
            for key, value in fields.items()
        }
        data["appsecret_proof"] = app_secret_proof(token, secret)
        result = self.request("POST", "/" + META_VERSION + "/act_" + account_id + "/" + edge, data, token, alive)
        try:
            return numeric(result.get("id"))
        except Invalid:
            raise Unconfirmed("Advertising object identity was not confirmed") from None

    def read_paid(self, kind, identity, token, secret, alive):
        numeric(identity)
        selectors = {
            "campaign": "id,account_id,status,effective_status,objective,is_adset_budget_sharing_enabled",
            "adset": "id,account_id,campaign_id,status,lifetime_budget,end_time,targeting,optimization_goal,billing_event",
            "creative": "id,account_id,object_story_id",
            "ad": "id,account_id,adset_id,status,effective_status,creative",
        }
        if kind not in selectors:
            raise Invalid("Unsupported advertising object")
        fields = {"fields": selectors[kind], "appsecret_proof": app_secret_proof(token, secret)}
        data = self.request("GET", "/" + META_VERSION + "/" + identity, fields, token, alive)
        if data.get("id") != identity:
            raise Unconfirmed("Advertising object readback was not confirmed")
        return data

    def set_paid_status(self, kind, identity, status, token, secret, alive):
        numeric(identity)
        if kind not in ("campaign", "adset", "ad") or status not in ("ACTIVE", "PAUSED"):
            raise Invalid("Unsupported advertising status change")
        fields = {"status": status, "appsecret_proof": app_secret_proof(token, secret)}
        result = self.request("POST", "/" + META_VERSION + "/" + identity, fields, token, alive)
        if result.get("success") is not True:
            raise Unconfirmed("Advertising status was not confirmed")
        return True

    def ad_insights(self, identity, token, secret, alive):
        numeric(identity)
        fields = {"fields": "spend", "date_preset": "maximum", "appsecret_proof": app_secret_proof(token, secret)}
        data = self.request("GET", "/" + META_VERSION + "/" + identity + "/insights", fields, token, alive)
        rows = data.get("data")
        if not isinstance(rows, list) or len(rows) > 1:
            raise Unconfirmed("Advertising spend readback was not confirmed")
        if not rows:
            return {"reported_spend": None, "reporting": "NO_ROWS"}
        value = rows[0].get("spend") if isinstance(rows[0], dict) else None
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,15}(?:\.[0-9]{1,6})?", value):
            raise Unconfirmed("Advertising spend readback was invalid")
        return {"reported_spend": value, "reporting": "PROVIDER_REPORTED_MAY_LAG"}
