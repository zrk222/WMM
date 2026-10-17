"""Current source, role and exact authorization boundaries for provider actions."""
from datetime import datetime, timezone
import json
from .common import Invalid, digest, iso_time
from .db import connection
from .review_access import exact_role
from .verified_reviews import source


def connection_row(db, app_id, identity):
    """Resolve only this app's connected App Store metadata without credentials."""
    row = db.execute("SELECT * FROM records WHERE app_id=? AND id=? AND kind='connection'", (app_id, identity)).fetchone()
    if not row:
        raise Invalid("Choose this app's App Store Connect connection")
    result = dict(row); result["data"] = json.loads(result["data"])
    if result["data"].get("provider") != "app_store" or result["data"].get("auth_mode") == "disconnected":
        raise Invalid("App Store connection is unavailable; reconnect before continuing")
    return result


def sources(db, app_id, record_id, connection_id):
    """Freeze full source and connection rows with the manifest version."""
    version, record = source(db, app_id, record_id)
    app = db.execute("SELECT data FROM apps WHERE id=?", (app_id,)).fetchone()
    manifest = json.loads(app["data"])
    if record["kind"] != "store" or record["data"].get("release") != manifest["release"] or record["data"].get("locale") != manifest["locale"]:
        raise Invalid("Choose store evidence for the workspace's current release and locale")
    return version, manifest, record, connection_row(db, app_id, connection_id)


def current(db, row):
    """Reject stale authorization, changed exact inputs and revoked role versions."""
    packet = json.loads(row["packet"])
    if digest(packet) != row["hash"] or (packet["app_id"], packet["preparer"], packet["expires"]) != (row["app_id"], row["preparer"], row["expires"]):
        raise Invalid("Provider action packet integrity changed")
    if iso_time(row["expires"]) <= datetime.now(timezone.utc):
        raise Invalid("Provider action approval expired; prepare a new baseline")
    version, _, record, conn = sources(db, row["app_id"], packet["record"]["id"], packet["connection"]["id"])
    if version != packet["manifest_version"] or record != packet["record"] or conn != packet["connection"]:
        raise Invalid("Provider action source or connection changed; prepare a new action")
    exact_role(db, row["app_id"], row["preparer"], packet["maker_role_version"], "MAKER")
    if row["checker"]:
        if row["checker"] == row["preparer"]:
            raise Invalid("Provider action maker and checker must differ")
        exact_role(db, row["app_id"], row["checker"], row["checker_role_version"], "CHECKER")
    return packet


def find(db, app_id, identity):
    """Reject an action from another workspace before any provider request."""
    row = db.execute("SELECT * FROM provider_actions WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
    if not row:
        raise Invalid("Provider action does not belong to this app")
    return row


def load(store, app_id, identity, enforce_current=True):
    """Return one immutable packet with optional write-authorization revalidation."""
    store.app(app_id)
    with connection(store.path) as db:
        row = find(db, app_id, identity)
        packet = current(db, row) if enforce_current else json.loads(row["packet"])
        if digest(packet) != row["hash"]:
            raise Invalid("Provider action packet integrity changed")
        return dict(row), packet
