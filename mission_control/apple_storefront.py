"""Credential-free lookup of one iOS listing in one storefront."""

import re
from typing import Any
from urllib.parse import urlencode, urlsplit

from .app_launch_status import StorefrontRead
from .common import Invalid, digest, now
from .providers import read_json


def storefront_code(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{2}", value):
        raise Invalid("Use a two-letter uppercase storefront code")
    return value


def lookup(store_id: str, storefront: str) -> tuple[StorefrontRead, str]:
    """Reduce a bounded Apple response to scoped presence; never return raw listing data."""
    country = storefront_code(storefront)
    if not re.fullmatch(r"[0-9]{1,30}", store_id):
        raise Invalid("Use the numeric App Store app ID")
    url = "https://itunes.apple.com/lookup?" + urlencode({"id": store_id, "country": country.lower()})
    payload: Any = read_json(url, {}, timeout=8)
    if not isinstance(payload, dict) or type(payload.get("resultCount")) is not int:
        raise Invalid("Apple lookup did not return a valid listing observation")
    rows = payload.get("results")
    if not isinstance(rows, list) or len(rows) > 1 or len(rows) != payload["resultCount"]:
        raise Invalid("Apple lookup returned ambiguous listing results")
    if not rows:
        return {"observed_at": now(), "storefront": country, "state": "NOT_LISTED"}, digest(payload)
    row = rows[0]
    if not isinstance(row, dict) or str(row.get("trackId")) != store_id or row.get("kind") != "software":
        raise Invalid("Apple lookup returned a different app")
    listing_url = row.get("trackViewUrl")
    if not isinstance(listing_url, str) or len(listing_url) > 2048:
        raise Invalid("Apple lookup did not confirm the selected storefront")
    try:
        parsed = urlsplit(listing_url)
    except ValueError:
        raise Invalid("Apple lookup did not confirm the selected storefront") from None
    if (
        parsed.scheme != "https"
        or parsed.netloc != "apps.apple.com"
        or not re.fullmatch(rf"/{country.lower()}/app/(?:[^/]+/)?id{store_id}/?", parsed.path)
    ):
        raise Invalid("Apple lookup did not confirm the selected storefront")
    return {"observed_at": now(), "storefront": country, "state": "AVAILABLE"}, digest(payload)
