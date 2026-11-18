"""Normalize only app-scoped purchase counts and Apple's estimated USD proceeds."""

import re
from decimal import Decimal

from .common import Invalid

REQUIRED_FIELDS = frozenset(("date", "app apple identifier", "purchase type", "purchases", "proceeds in usd"))
TYPES = {"app purchase", "in-app purchases"}


def _usd(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[+-]?\d{1,18}(?:\.\d{1,18})?(?:[eE][+-]?\d{1,2})?", value, re.ASCII
    ):
        raise Invalid("Apple purchase proceeds require a finite USD decimal")
    amount = Decimal(value)
    exponent = amount.as_tuple().exponent
    if not isinstance(exponent, int) or (amount and (amount.adjusted() > 17 or exponent < -18)):
        raise Invalid("Apple purchase proceeds exceed the supported decimal precision")
    if not amount:
        return "0"
    amount_text = format(amount, "f")
    return amount_text.rstrip("0").rstrip(".") if "." in amount_text else amount_text


def observation(row: dict[str, str], day: str) -> dict:
    purchases = row["purchases"]
    if not re.fullmatch(r"-?[0-9]{1,15}", purchases) or not row["purchase type"].strip():
        raise Invalid("Invalid Apple purchase report count or purchase type")
    label = row["purchase type"].strip().casefold()
    return dict(
        date=day,
        type="purchase",
        source_type=label if label in TYPES else "other",
        count=int(purchases),
        dimensions={},
        proceeds_usd=_usd(row["proceeds in usd"]),
    )


def validate_observation(row: dict) -> None:
    if (
        row["type"] != "purchase"
        or row["source_type"] not in (*TYPES, "other")
        or type(row["count"]) is not int
        or abs(row["count"]) > 999999999999999
        or row["proceeds_usd"] != _usd(row["proceeds_usd"])
        or row["dimensions"] != {}
    ):
        raise Invalid("Invalid saved Apple purchase observation")
