"""Owner-recorded checking effort, never inferred from provider call counts."""

from sqlite3 import Connection

from .common import Invalid, iso_time
from .marketing_review_store import rows


def summary(db: Connection, app: str, owner: str, scope: str, window: dict) -> dict:
    """Half-open event windows prevent double counting at adjacent boundaries."""
    start, end = (iso_time(window[key]) for key in ("starts_at", "ends_at"))
    events = [
        row for row in rows(db, app, owner, scope, "EFFORT") if start <= iso_time(row["data"]["occurred_at"]) < end
    ]
    fields = ("checks_run", "reviews_completed", "minutes")
    return dict(
        status="OWNER_RECORDED" if events else "NOT_RECORDED",
        period=window,
        **{key: sum(row["data"][key] for row in events) if events else None for key in fields},
        evidence_hashes=[row["hash"] for row in events],
        limits="Recorded effort only, not automatic time tracking, billing or total campaign cost.",
    )


def validate(body: dict) -> dict:
    """Require bounded counts and explicit supporting evidence, including real zeroes."""
    from .common import required
    from .pmf_contract import hashed

    for key in ("checks_run", "reviews_completed", "minutes"):
        if type(body[key]) is not int or not 0 <= body[key] <= 100000:
            raise Invalid("Record nonnegative whole verification counts and minutes")
    return dict(
        occurred_at=iso_time(body["occurred_at"]).isoformat(),
        checks_run=body["checks_run"],
        reviews_completed=body["reviews_completed"],
        minutes=body["minutes"],
        evidence_sha256=hashed(body["evidence_sha256"]),
        note=required(body["note"], "Effort evidence note", 2000),
    )
