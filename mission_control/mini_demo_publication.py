"""Approval-time gate for rendered mini-demos, without issuing publication authority."""

from sqlite3 import Connection
from typing import Any

from .campaign_stale_claims import source_snapshot
from .common import Invalid
from .creative_analysis import latest
from .creative_briefs import stale_findings
from .marketing_review_store import decoded
from .mini_demo import hook_review


def check(db: Connection, store: Any, app: str, draft: dict) -> None:
    """A registered demo needs the reviewed hook, current feature and exact post tag."""
    artifact = draft.get("artifact")
    if not artifact:
        return
    row = db.execute("SELECT data FROM hypit_renders WHERE app_id=? AND id=?", (app, artifact["id"])).fetchone()
    if row is None:
        return
    import json

    brief_hash = json.loads(row["data"])["inputs"]["request"]["brief_hash"]
    candidates = []
    for saved in db.execute("SELECT * FROM marketing_review_evidence WHERE app_id=? AND kind='DEMO'", (app,)):
        demo = decoded(saved)
        data = demo["data"]
        if data["brief_hash"] != brief_hash:
            continue
        candidates.append(demo)
        if data["channel"] != draft["provider"] or data["tagged_link"] != draft["link"]:
            continue
        hook_review(data["hook_review"], brief_hash)
        brief = latest(db, "creative_briefs", app, data["brief_id"])
        if brief["hash"] != brief_hash or stale_findings(db, store, app, brief["data"]):
            raise Invalid("Mini-demo creative changed; repeat the hook and product review")
        change = db.execute(
            "SELECT * FROM marketing_review_evidence WHERE app_id=? AND owner=? AND kind='CHANGE' AND id=?",
            (app, saved["owner"], data["change_id"]),
        ).fetchone()
        changed = decoded(change)
        source = changed["data"]["source"]
        if changed["hash"] != data["change_hash"] or source_snapshot(db, app, list(source["claims"])) != source:
            raise Invalid("Mini-demo shipped-feature proof changed; review current claims")
        return
    if candidates:
        raise Invalid("Use the mini-demo's exact channel-specific link before approval")
