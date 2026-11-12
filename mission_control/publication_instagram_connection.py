"""Read-only Page and Instagram account binding for Facebook Login publishing."""

import json, re, time
from .common import Invalid
from .social_auth import app_secret_proof
from .social_contract import display, opaque
from .social_profiles import facebook, selected_page
from .social_transport import request

REQUIRED = {"instagram_basic", "instagram_content_publish"}


def _numeric(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,32}", value):
        raise Invalid("Invalid Facebook or Instagram account")
    return value


def _saved_data(connectionrow):
    """Decode and validate the saved connection JSON without accepting other shapes."""
    data = connectionrow.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            raise Invalid("Invalid saved Facebook connection") from None
    if not isinstance(data, dict):
        raise Invalid("Invalid saved Facebook connection")
    return data


def _saved_page(connectionrow, draft, data):
    """Require the same live Page, connection revision, and publishing scopes."""
    if (
        connectionrow.get("provider") != "facebook"
        or connectionrow.get("status") != "CONNECTED_READ_TESTED"
        or connectionrow.get("lease")
        or connectionrow.get("app_id") != draft.get("app_id")
        or connectionrow.get("id") != draft.get("connection_id")
        or connectionrow.get("version") != draft.get("connection_version")
        or (connectionrow.get("expires") is not None and connectionrow["expires"] <= time.time())
    ):
        raise Invalid("Facebook Page connection changed or expired")
    dest = data.get("destination")
    identity = data.get("identity")
    if (
        not isinstance(dest, dict)
        or dest.get("kind") != "PAGE"
        or not isinstance(identity, dict)
        or not isinstance(identity.get("permissions"), list)
        or not REQUIRED.issubset(identity["permissions"])
    ):
        raise Invalid("Reconnect Facebook Page with Instagram publishing permissions")
    if draft.get("provider") != "instagram":
        raise Invalid("Publication channel changed")
    _numeric(draft.get("destination_id"))
    return _numeric(dest.get("id"))


def assert_saved_connection(connectionrow, draft):
    """Bind an Instagram draft to its unchanged Facebook Page and linked account."""
    row = dict(connectionrow)
    data = _saved_data(row)
    return _saved_page(row, draft, data)


def _verify_page_access(found, page_id):
    """Require current Facebook permissions and membership of the selected Page."""
    if not REQUIRED.issubset(found.permissions or []) or not any(page["id"] == page_id for page in found.destinations):
        raise Invalid("Facebook Page permissions changed")


def _verify_instagram_response(raw, page_id, expected_ig_id):
    """Check the provider response and optional expected Instagram account ID."""
    if (
        not isinstance(raw, dict)
        or str(raw.get("id")) != page_id
        or not isinstance(raw.get("instagram_business_account"), dict)
    ):
        raise Invalid("Facebook Page has no verified Instagram professional account")
    ig = raw["instagram_business_account"]
    identity = _numeric(str(ig.get("id")))
    if expected_ig_id is not None and identity != expected_ig_id:
        raise Invalid("Linked Instagram account changed")
    return {"id": identity, "username": display(ig.get("username")), "page_id": page_id}


def inspect(config, client_secret, credentials, page_id, expected_ig_id=None, alive=lambda: None):
    """Verify actual user permissions and Page relationship; return no token in public mapping."""
    page_id = _numeric(page_id)
    if expected_ig_id is not None:
        _numeric(expected_ig_id)
    if (
        not isinstance(config, dict)
        or config.get("provider") != "facebook"
        or not REQUIRED.issubset(config.get("scopes", []))
    ):
        raise Invalid("Reconnect Facebook Page with Instagram publishing permissions")
    if not isinstance(credentials, dict):
        raise Invalid("Facebook credentials unavailable")
    access = opaque(credentials.get("access_token"))
    opaque(credentials.get("page_token"), "Page access token")
    found = facebook(config, client_secret, access, alive)
    _verify_page_access(found, page_id)
    page, token = selected_page(client_secret, access, page_id, alive)
    raw = request(
        "facebook",
        "instagram_account",
        {"account": page_id, "appsecret_proof": app_secret_proof(token, client_secret)},
        bearer=token,
        alive=alive,
    )
    return _verify_instagram_response(raw, page_id, expected_ig_id), token
