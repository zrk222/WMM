"""Real read-only Apple API adapters, fixed hosts and app-specific references."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from .common import Invalid, required, now, digest
from .apple_ads_preflight import ENDPOINT, inventory_request, shape_inventory


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Block provider redirects so credentials cannot follow an untrusted destination."""
        raise Invalid("Provider redirect blocked; verify the documented endpoint")


def credential(binding, app_id):
    """Resolve only a credential environment reference scoped to this app."""
    if binding.get("auth_mode")=="disconnected":
        raise Invalid("Connection is disconnected; open provider setup to reconnect")
    if binding.get("credential_ref"):
        from .provider_auth import credential as protected_credential
        return protected_credential(binding,app_id)
    name=required(binding.get("env_ref"),"Environment reference",120)
    prefix="GROWTH_"+app_id.upper().replace("-","_")+"_"
    if not re.fullmatch(r"[A-Z][A-Z0-9_]+",name) or not name.startswith(prefix):
        raise Invalid(f"Use a separate environment reference beginning {prefix}")
    value=os.environ.get(name)
    if not value:
        raise Invalid(f"Set {name} on the local server and restart it. No credential is stored in the browser.")
    return value


def read_json(url, headers):
    """Read a fixed provider endpoint with bounded time and response size."""
    request=Request(url,headers=dict(headers,Accept="application/json"),method="GET")
    try:
        with build_opener(NoRedirect()).open(request,timeout=15) as response:
            raw=response.read(2097153)
    except HTTPError as exc:
        raise Invalid(f"Provider returned HTTP {exc.code}. Check permissions, token expiry and account identity; no data was fabricated.") from exc
    except URLError as exc:
        raise Invalid("Provider could not be reached. Check the connection and retry this read.") from exc
    if len(raw)>2097152:
        raise Invalid("Provider response exceeds 2 MB; narrow the query or use an export")
    return json.loads(raw)


def report_destination(url,body):
    """Verify method-specific fixed destinations before creating an authenticated request."""
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.netloc!=parsed.hostname or parsed.fragment:
        raise Invalid("Unapproved provider report destination")
    query_paths=("/v1/campaigns/query","/v1/reports/apps/campaigns/query","/v1/reports/apps/keywords/query","/v1/reports/apps/searchterms/query")
    allowed=False
    if parsed.hostname=="api.appstoreconnect.apple.com":
        apple_paths = r'/v1/(?:apps/\d+(?:/customerReviews|/subscriptionGroups)?|subscriptionGroups/\d+/subscriptions|appStoreVersions/[A-Za-z0-9-]{1,80}(?:/appStoreVersionLocalizations)?|appStoreVersionLocalizations/[A-Za-z0-9-]{1,80}/appScreenshotSets|appScreenshotSets/[A-Za-z0-9-]{1,80}/appScreenshots)'
        allowed=body is None and re.fullmatch(apple_paths,parsed.path)
    if parsed.hostname=="api.ads.apple.com":
        allowed=parsed.path in query_paths and body is not None and not parsed.query
    if not allowed:
        raise Invalid("Unapproved provider report destination")


def report_bytes(request,timeout):
    """Fetch bounded bytes with redirects blocked and readable provider errors."""
    try:
        with build_opener(NoRedirect()).open(request,timeout=min(15,timeout)) as response:
            raw=response.read(2097153)
    except HTTPError as exc:
        raise Invalid(f"Provider HTTP {exc.code}; check permission, expiry or rate limits and retry this read") from exc
    except (URLError,TimeoutError) as exc:
        raise Invalid("Provider read failed or timed out; saved work is preserved") from exc
    if len(raw)>2097152:
        raise Invalid("Provider response exceeds 2 MB; narrow the report")
    return raw


def report_request(url,headers,body=None,timeout=15):
    """Read approved report endpoints only; query POST cannot mutate a campaign."""
    report_destination(url,body)
    data=json.dumps(body,allow_nan=False).encode() if body is not None else None
    request=Request(url,data=data,headers=dict(headers,Accept="application/json",**{"Content-Type":"application/json"}),method="POST" if data is not None else "GET")
    raw=report_bytes(request,timeout)
    try:
        payload=json.loads(raw)
    except (UnicodeError,ValueError) as exc:
        raise Invalid("Provider returned malformed JSON") from exc
    if not isinstance(payload,dict) or payload.get("error") or payload.get("errors"):
        raise Invalid("Provider report failed; inspect its permissions and current API contract")
    return payload


def sync(binding, app_id):
    """Read the current scoped Ads inventory or the selected App Store identity."""
    provider=binding.get("provider")
    if provider=="apple_ads":
        store,account,body=inventory_request(binding)
        headers={"Authorization":"Bearer "+credential(binding,app_id),"X-AP-Context":"adAccountId="+account}
        payload=shape_inventory(report_request(ENDPOINT,headers,body),store,account)
        return {"provider":provider,"app_id":app_id,"observed_at":now(),"endpoint":ENDPOINT,
                "api_version":"PLATFORM_V1","store_app_id":store,"account_id":account,
                "payload":payload,"campaign_ids":payload["campaign_ids"],"coverage":payload["coverage"],
                "source_hash":digest(payload),"external_writes":False,
                "scope":"Read-only scoped inventory; no app eligibility, delivery or acquisition outcome inferred",
                "pagination":"First bounded page only; PARTIAL means more campaigns exist"}
    if provider!="app_store":
        raise Invalid("This connection uses manual observation import. Use the evidence worksheet.")
    store_id=required(binding.get("store_app_id"),"Store app ID",30)
    if not store_id.isdigit():
        raise Invalid("App Store ID must be numeric")
    headers={"Authorization":"Bearer "+credential(binding,app_id)}
    url=f"https://api.appstoreconnect.apple.com/v1/apps/{store_id}?include=appStoreVersions"
    payload=scope_payload(read_json(url,headers),provider,store_id)
    return {"provider":provider,"app_id":app_id,"observed_at":now(),"endpoint":url,
            "payload":payload,"scope":"Read-only response; campaign delivery and acquisition results not inferred",
            "pagination":"First bounded page; inspect provider links/pagination before a completeness claim"}


def scope_payload(payload,provider,store_id):
    """Reject mismatched Store identity and exclude other apps' campaigns."""
    if provider=="app_store":
        if str(payload.get("data",{}).get("id"))!=store_id:
            raise Invalid("Provider returned a different app identity")
        return payload
    source=payload.get("data",[])
    if not isinstance(source,list):
        raise Invalid("Campaign response shape is unrecognized; inspect the current API contract")
    scoped=[campaign for campaign in source if str(campaign.get("adamId"))==store_id]
    return {"data":scoped,"pagination":payload.get("pagination"),"other_app_campaigns_excluded":True}
