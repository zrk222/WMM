"""Immutable batch lineage and current retained execution authority."""
import json

from .common import Invalid, digest


def bound_plan(row):
    """Detect modification of either the reviewed plan or its retained authority."""
    envelope = json.loads(row["plan"])
    if (set(envelope) != {"plan", "authority", "binding_hash"}
            or digest(envelope["plan"]) != row["plan_hash"]
            or envelope["binding_hash"] != digest([row["plan_hash"], envelope["authority"]])):
        raise Invalid("The saved batch or its authority changed")
    return envelope


def guard_batch(db, store, row):
    """Recheck retained authority and manifest at a transaction boundary."""
    from .agent_grants import check_batch_authority
    envelope = bound_plan(row)
    app = db.execute("SELECT version FROM apps WHERE id=?", (row["app_id"],)).fetchone()
    if not app or app["version"] != envelope["plan"]["manifest_version"]:
        raise Invalid("The batch app changed")
    check_batch_authority(db, store, row["app_id"], envelope["authority"], row["plan_hash"])
    return envelope


def guard_render(db, store, job):
    """Require a current batch and retained grant for every linked render attempt."""
    row = db.execute("SELECT b.* FROM creative_batches b JOIN creative_batch_variants v "
        "ON v.app_id=b.app_id AND v.batch_id=b.id WHERE v.app_id=? AND v.job_id=?",
        (job["app_id"], job["id"])).fetchone()
    if row is None:
        return
    if row["state"] != "ACTIVE":
        raise Invalid("The batch was cancelled or stopped")
    guard_batch(db, store, row)
