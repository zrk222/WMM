"""Opt-in local notices with durable deduplication; a terminal channel, not browser UI."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import Invalid, digest, iso_time, now
from .db import connection
from .store import Store

HORIZON = timedelta(days=7)
KINDS = ("JOB", "AGENT_GRANT", "CAMPAIGN_MONITOR", "APPLE_SCHEDULE", "OBSERVATIONAL_STUDY")


def enabled(store, app_id):
    """Notices are quiet by default until the local operator opts in."""
    store.app(app_id)
    with connection(store.path) as db:
        row = db.execute("SELECT enabled FROM notice_settings WHERE app_id=?", (app_id,)).fetchone()
    return bool(row and row["enabled"])


def configure(store, app_id, value):
    """Persist one explicit owner-machine opt-in without granting any authority."""
    if type(value) is not bool:
        raise Invalid("Notice opt-in must be an explicit boolean")
    store.app(app_id)
    with connection(store.path) as db:
        db.execute("INSERT INTO notice_settings(app_id,enabled,updated) VALUES(?,?,?) "
                   "ON CONFLICT(app_id) DO UPDATE SET enabled=excluded.enabled,updated=excluded.updated",
                   (app_id, int(value), now()))
    return enabled(store, app_id)


def _candidate(kind, identity, title, state, observed):
    return dict(id=digest([kind, str(identity), state]), kind=kind, title=title, state=state, observed_at=observed)


def collect(store, app_id):
    """Project bounded durable rows into notices without payloads or private messages."""
    store.app(app_id)
    current = datetime.now(timezone.utc)
    with connection(store.path) as db:
        items = []
        for row in db.execute("SELECT id,action,status,updated FROM jobs WHERE app_id=? "
                              "AND status IN ('FAILED','BLOCKED','INTERRUPTED') ORDER BY updated DESC,id DESC LIMIT 50",
                              (app_id,)):
            items.append(_candidate("JOB", row["id"], "Saved run needs attention", row["status"], row["updated"]))
        for row in db.execute("SELECT id,expires,updated FROM agent_grants WHERE app_id=? "
                              "AND status='ACTIVE' ORDER BY expires,id LIMIT 50", (app_id,)):
            try:
                expires = iso_time(row["expires"])
            except Invalid:
                continue
            if current < expires <= current + HORIZON:
                items.append(_candidate("AGENT_GRANT", row["id"], "Owner grant expires soon", "EXPIRING", row["updated"]))
        for row in db.execute("SELECT id,status,updated FROM campaign_monitors WHERE app_id=? "
                              "AND status='BLOCKED' ORDER BY updated DESC,id DESC LIMIT 50", (app_id,)):
            items.append(_candidate("CAMPAIGN_MONITOR", row["id"], "Campaign monitor is blocked", row["status"], row["updated"]))
        for row in db.execute("SELECT app_id,status,updated FROM apple_metrics_schedules WHERE app_id=? "
                              "AND status='BLOCKED' LIMIT 5", (app_id,)):
            items.append(_candidate("APPLE_SCHEDULE", row["app_id"], "Apple analytics schedule is blocked",
                                    row["status"], row["updated"]))
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                      "AND name='observational_campaign_studies'").fetchone():
            for row in db.execute("SELECT study_id,data,registered_at FROM observational_campaign_studies "
                                  "WHERE app_id=? ORDER BY registered_at DESC,study_id LIMIT 50", (app_id,)):
                try:
                    ends = iso_time(json.loads(row["data"])["ends_at"])
                except (Invalid, KeyError, TypeError, ValueError):
                    continue
                if ends <= current:
                    state, title = "ENDED", "Tagged study window ended — read results"
                elif ends <= current + HORIZON:
                    state, title = "ENDING_SOON", "Tagged study window ends soon"
                else:
                    continue
                items.append(_candidate("OBSERVATIONAL_STUDY", row["study_id"], title, state, row["registered_at"]))
    return sorted(items, key=lambda item: (item["kind"], item["id"]))


def sync(store, app_id):
    """Retain new notices once; repeated collection is idempotent across restarts."""
    if not enabled(store, app_id):
        return []
    items = collect(store, app_id)
    with connection(store.path) as db:
        for item in items:
            db.execute("INSERT OR IGNORE INTO notices(app_id,id,kind,title,state,created) VALUES(?,?,?,?,?,?)",
                       (app_id, item["id"], item["kind"], item["title"], item["state"], now()))
    return pending(store, app_id)


def pending(store, app_id):
    """Return undelivered notices only; the delivered history is retained."""
    with connection(store.path) as db:
        rows = [dict(row) for row in db.execute(
            "SELECT id,kind,title,state,created FROM notices WHERE app_id=? AND delivered_at IS NULL "
            "ORDER BY created,id LIMIT 100", (app_id,))]
    return rows


def deliver(store, app_id, notifier):
    """Deliver once and record the outcome; a failed or dismissed notice never repeats."""
    results = []
    for item in pending(store, app_id):
        try:
            outcome = "DELIVERED" if notifier(item) is not False else "DELIVERY_FAILED"
        except Exception:
            outcome = "DELIVERY_FAILED"
        with connection(store.path) as db:
            db.execute("UPDATE notices SET delivered_at=?,outcome=? WHERE app_id=? AND id=? AND delivered_at IS NULL",
                       (now(), outcome, app_id, item["id"]))
        results.append(dict(item, outcome=outcome))
    return results


def dismiss(store, app_id, identity):
    """An explicit dismissal marks the notice handled so it never repeats."""
    if not isinstance(identity, str) or not identity:
        raise Invalid("Choose one saved notice")
    with connection(store.path) as db:
        changed = db.execute("UPDATE notices SET delivered_at=?,outcome='DISMISSED' "
                             "WHERE app_id=? AND id=? AND delivered_at IS NULL", (now(), app_id, identity)).rowcount
    if changed != 1:
        raise Invalid("Notice is unknown or already handled")
    return status(store, app_id)


def status(store, app_id):
    """Report opt-in and outcome counts without any notice payload."""
    store.app(app_id)
    with connection(store.path) as db:
        counts = {row["outcome"]: row["n"] for row in db.execute(
            "SELECT outcome,count(*) AS n FROM notices WHERE app_id=? GROUP BY outcome", (app_id,))}
    return dict(app_id=app_id, enabled=enabled(store, app_id), pending=counts.get(None, 0),
                delivered=counts.get("DELIVERED", 0), failed=counts.get("DELIVERY_FAILED", 0),
                dismissed=counts.get("DISMISSED", 0),
                channel="LOCAL_TERMINAL", scope="Saved local operational state only; no provider read or browser dependency.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Opt-in local WMM notices")
    parser.add_argument("--database", required=True, help="Path to the local WMM SQLite database")
    parser.add_argument("--app", required=True, help="App workspace identity")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--once", action="store_true")
    group.add_argument("--dismiss", metavar="NOTICE_ID")
    args = parser.parse_args(argv)
    if not Path(args.database).is_file():
        parser.error("--database must point to an existing local WMM database")
    store = Store(Path(args.database), seed=False)
    if args.dismiss:
        print(dismiss(store, args.app, args.dismiss))
        return 0
    if args.enable or args.disable:
        print(dict(app_id=args.app, enabled=configure(store, args.app, args.enable)))
        return 0
    if args.once:
        if not enabled(store, args.app):
            print("Notices are disabled for this app. Run with --enable to opt in.")
            return 0
        sync(store, args.app)
        for item in deliver(store, args.app, lambda notice: print(
                notice["kind"] + ": " + notice["title"] + " · " + notice["state"])):
            print("delivered", item["id"], item["outcome"])
        return 0
    print(status(store, args.app))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
