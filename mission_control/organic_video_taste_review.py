"""Owner-delegated, agent-attested output judgment; never rights or visual certification."""

from datetime import datetime, timezone
import math

from .agent_grants import current
from .campaign_contract import exact, hashes
from .common import Invalid, digest, iso_time, required
from .creative_taste import guidance
from .social_contract import reference

CHECKS = ("opening", "captions", "framing", "timing", "audio", "claims", "cta", "source_identity")


def setting(value, mode):
    exact(value, ("reviewer_grant_id", "guidance_sha256", "rules"))
    if mode != "STANDING_GENERATED":
        raise Invalid("Delegated taste approval requires standing-generated mode")
    reference(value["reviewer_grant_id"])
    hashes([value["guidance_sha256"]], True)
    required(value["rules"], "Owner taste rules", 4000)
    if not value["rules"].strip():
        raise Invalid("Write useful owner taste rules")
    return dict(value)


def selected_grant(db, app_id, owner, value):
    if value["guidance_sha256"] != guidance()["policy_sha256"]:
        raise Invalid("Taste guidance changed; review a new policy")
    row = db.execute("SELECT * FROM agent_grants WHERE id=?", (value["reviewer_grant_id"],)).fetchone()
    if row is None or row["owner"] != owner:
        raise PermissionError("Choose an active reviewer delegated by this owner")
    current(
        db,
        row,
        dict(app_id=app_id, operation="organic-video.policy-admit"),
        datetime.now(timezone.utc),
        check_quota=False,
    )
    return row


def attest(db, app_id, saved, context, output, duration):
    value = saved["data"]["policy"].get("taste_auto_review")
    if value is None:
        return
    selected_grant(db, app_id, saved["data"]["owner"], value)
    if context.get("grant_id") != value["reviewer_grant_id"]:
        raise PermissionError("Only the owner-selected taste reviewer can attest this output")
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise Invalid("Actual output duration is unavailable; HOLD for missing evidence")
    review = output.get("taste_review")
    exact(
        review,
        ("policy_hash", "artifact_sha256", "rules_sha256", "guidance_sha256", "verdict", "reviewed_at", "checks"),
    )
    if (
        review["policy_hash"] != saved["hash"]
        or review["artifact_sha256"] != output["artifact_sha256"]
        or review["rules_sha256"] != digest(value["rules"])
        or review["guidance_sha256"] != value["guidance_sha256"]
    ):
        raise Invalid("Taste review differs from the selected output, rules or policy")
    reviewed = iso_time(review["reviewed_at"])
    if reviewed > datetime.now(timezone.utc) or reviewed < iso_time(saved["created"]):
        raise Invalid("Taste review timestamp is outside this policy")
    if review["verdict"] not in ("PASS", "REVISE", "HOLD"):
        raise Invalid("Select PASS, REVISE or HOLD")
    rows = review["checks"]
    if not isinstance(rows, list) or len(rows) != len(CHECKS):
        raise Invalid("Missing mandatory taste evidence requires HOLD")
    seen = set()
    for row in rows:
        exact(row, ("id", "status", "at_seconds", "observation", "fix"))
        if row["id"] not in CHECKS or row["id"] in seen:
            raise Invalid("Use every mandatory taste check exactly once")
        seen.add(row["id"])
        at = row["at_seconds"]
        if type(at) not in (int, float) or not math.isfinite(at) or not 0 <= at < duration:
            raise Invalid("Taste observations must identify actual output timestamps")
        required(row["observation"], "Observed frame or audio evidence", 2000)
        if not row["observation"].strip():
            raise Invalid("Unknown taste evidence requires HOLD")
        if not isinstance(row["fix"], str) or len(row["fix"]) > 2000:
            raise Invalid("Use a bounded corrective action")
        if row["status"] != "PASS" or review["verdict"] != "PASS":
            raise Invalid("Taste defects or missing evidence require revision or HOLD before admission")


def choices(db, app_id, owner):
    result = []
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='agent_grants'").fetchone():
        return result
    for row in db.execute("SELECT * FROM agent_grants WHERE app_id=? AND owner=?", (app_id, owner)):
        try:
            current(db, row, dict(app_id=app_id, operation="organic-video.policy-admit"), datetime.now(timezone.utc))
        except (Invalid, PermissionError):
            continue
        result.append(dict(id=row["id"], agent_id=row["agent_id"]))
    return result
