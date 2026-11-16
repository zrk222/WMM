"""Validate the bounded public App Store format without changing its wire URL."""

import re
from urllib.parse import SplitResult, parse_qsl

from .common import Invalid

HOST = "apps.apple.com"
PRODUCT = re.compile(r"/(?:[a-z]{2}/)?app/(?:[a-z0-9-]+/)?id([0-9]{1,30})/?")
PUNCTUATION = frozenset(" []/\\-~+=<>:;,._‘“*&$%#@?!|{}()")


def campaign_token(value: str) -> bool:
    """Accept documented Apple token characters and length, without trimming."""
    return (
        1 <= len(value) <= 30
        and value == value.strip()
        and all(char.isalnum() or char in PUNCTUATION for char in value)
    )


def campaign_parts(url: SplitResult) -> tuple[str, str] | None:
    """Return the app ID and Apple token, or None for a non-Apple tracking URL."""
    if url.hostname != HOST or not set(re.findall(r"(?:^|&)([^=&]+)=", url.query)) & {"pt", "ct", "mt", "app"}:
        return None
    product = PRODUCT.fullmatch(url.path)
    if url.scheme != "https" or url.netloc not in (HOST, HOST + ":443") or url.fragment or not product:
        raise Invalid("Use an official Apple product campaign link")
    try:
        if not re.fullmatch(r"(?:[A-Za-z0-9._~+=&-]|%[0-9A-Fa-f]{2})+", url.query):
            raise ValueError()
        fields = parse_qsl(url.query, keep_blank_values=True, strict_parsing=True, errors="strict", max_num_fields=4)
    except (ValueError, UnicodeError):
        raise Invalid("Invalid Apple campaign parameters") from None
    params = dict(fields)
    if (
        len(params) != len(fields)
        or not {"pt", "ct"}.issubset(params)
        or set(params) - {"pt", "ct", "mt", "app"}
        or not re.fullmatch(r"[0-9]{1,20}", params["pt"])
        or not campaign_token(params["ct"])
        or params.get("mt", "8") != "8"
        or params.get("app", "messages") != "messages"
    ):
        raise Invalid("Invalid Apple campaign parameters")
    return product[1], params["ct"]
