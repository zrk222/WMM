"""Durable browser-instrumentation lifecycle; downloads and attestations are not delivery."""
import json
import re
from datetime import datetime, timezone

from .common import Invalid, canonical, digest, iso_time, now, required
from .db import connection

STATES = ("DOWNLOADED", "REPORTED_INSTALLED", "PROBE_OBSERVED")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
HEX = re.compile(r"[a-f0-9]{64}")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
PROVIDER = re.compile(r"[A-Z][A-Z0-9_]{0,31}")


def decoded(row):
    """Decode one immutable receipt without exposing any other stored field."""
    value = dict(row)
    value["data"] = json.loads(value["data"])
    return value


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid("Use the exact instrumentation lifecycle fields")
    return value


def _text(value, name, limit):
    text = required(value, name, limit)
    if CONTROL.search(text):
        raise Invalid(name + " cannot contain control characters")
    return text


def _time(value, name, *, after=None):
    try:
        at = iso_time(value)
    except Exception as exc:
        raise Invalid(name + " must be an ISO timestamp") from exc
    current = datetime.now(timezone.utc)
    if at > current:
        raise Invalid(name + " cannot be in the future")
    if after is not None and at < after:
        raise Invalid(name + " cannot precede the previous report")
    return at


def _insert(db, app_id, identity, experiment_id, proposal_hash, bundle_hash, state, data, previous_id, stamp):
    hashed = digest(data)
    db.execute("INSERT INTO instrumentation_receipts VALUES(?,?,?,?,?,?,?,?,?,?)",
               (app_id, identity, experiment_id, proposal_hash, bundle_hash, state,
                previous_id, canonical(data), hashed, stamp))
    return dict(app_id=app_id, id=identity, experiment_id=experiment_id, proposal_hash=proposal_hash,
                bundle_hash=bundle_hash, state=state, previous_id=previous_id, data=data,
                hash=hashed, created=stamp, schema="growth.instrumentation-receipt.v1")


def _prior(db, app_id, experiment_id, identity, value_hash, state):
    row = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=? AND experiment_id=?",
                     (app_id, identity, experiment_id)).fetchone()
    if row is None or row["state"] != state or row["hash"] != value_hash:
        raise Invalid("Select this app's exact previous instrumentation receipt")
    return decoded(row)


def record_download(store, app_id, experiment_id, proposal_hash, bundle_hash):
    """Retain one idempotent download receipt; never imply installation."""
    store.app(app_id)
    for value in (experiment_id, proposal_hash, bundle_hash):
        if not isinstance(value, str) or not value:
            raise Invalid("Instrumentation identity is invalid")
    if not HEX.fullmatch(bundle_hash):
        raise Invalid("Instrumentation bundle hash is invalid")
    identity = digest(["DOWNLOADED", app_id, experiment_id, proposal_hash, bundle_hash])
    stamp = now()
    data = dict(state="DOWNLOADED", experiment_id=experiment_id, proposal_hash=proposal_hash,
                bundle_hash=bundle_hash, report="BUNDLE_GENERATED_AND_DOWNLOADED",
                scope="Downloading does not install code, launch variants or verify delivery.")
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        saved = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=?",
                           (app_id, identity)).fetchone()
        if saved:
            return decoded(saved)
        return _insert(db, app_id, identity, experiment_id, proposal_hash, bundle_hash,
                       "DOWNLOADED", data, None, stamp)


def record_installed(store, app_id, experiment_id, body):
    """Append an owner-reported installation attestation for the exact downloaded bundle."""
    app = store.app(app_id)
    _exact(body, {"proposal_hash", "downloaded_id", "downloaded_hash", "release", "install_reference", "reported_at"})
    release = _text(body["release"], "Release", 100)
    if release != app["data"].get("release"):
        raise Invalid("Report installation against the current app release")
    reference = _text(body["install_reference"], "Installation reference", 200)
    reported = _time(body["reported_at"], "Reported time")
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        prior = _prior(db, app_id, experiment_id, body["downloaded_id"], body["downloaded_hash"], "DOWNLOADED")
        if prior["data"]["proposal_hash"] != body["proposal_hash"]:
            raise Invalid("Installation does not match this downloaded proposal")
        if reported < iso_time(prior["created"]):
            raise Invalid("Reported time cannot precede the download")
        identity = digest(["REPORTED_INSTALLED", prior["id"], reference, reported.isoformat()])
        saved = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=?",
                           (app_id, identity)).fetchone()
        if saved:
            return decoded(saved)
        data = dict(state="REPORTED_INSTALLED", experiment_id=experiment_id,
                    proposal_hash=body["proposal_hash"], bundle_hash=prior["bundle_hash"],
                    previous_id=prior["id"], previous_hash=prior["hash"], release=release,
                    install_reference=reference, reported_at=reported.isoformat(),
                    report="OWNER_ATTESTED_NOT_VERIFIED_DELIVERY")
        return _insert(db, app_id, identity, experiment_id, body["proposal_hash"],
                       prior["bundle_hash"], "REPORTED_INSTALLED", data, prior["id"], now())


def record_probe(store, app_id, experiment_id, body):
    """Append one owner-reported live probe with exact identity, time and scope."""
    app = store.app(app_id)
    _exact(body, {"previous_id", "previous_hash", "provider", "event_id", "observed_at",
                  "scope", "source_receipt_sha256", "release"})
    release = _text(body["release"], "Release", 100)
    if release != app["data"].get("release"):
        raise Invalid("Probe against the current app release")
    provider = body["provider"]
    if not isinstance(provider, str) or not PROVIDER.fullmatch(provider):
        raise Invalid("Provider must be an uppercase token")
    event = body["event_id"]
    if not isinstance(event, str) or not TOKEN.fullmatch(event):
        raise Invalid("Probe event identity is invalid")
    scope = _text(body["scope"], "Probe scope", 500)
    source = body["source_receipt_sha256"]
    if not isinstance(source, str) or not HEX.fullmatch(source):
        raise Invalid("Probe source receipt must be a lowercase SHA-256")
    observed = _time(body["observed_at"], "Observed time")
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        prior = _prior(db, app_id, experiment_id, body["previous_id"], body["previous_hash"], "REPORTED_INSTALLED")
        if observed < iso_time(prior["data"]["reported_at"]):
            raise Invalid("Probe time cannot precede the installation report")
        identity = digest(["PROBE_OBSERVED", prior["id"], provider, event, observed.isoformat(), source])
        saved = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=?",
                           (app_id, identity)).fetchone()
        if saved:
            return decoded(saved)
        data = dict(state="PROBE_OBSERVED", experiment_id=experiment_id,
                    proposal_hash=prior["data"]["proposal_hash"], bundle_hash=prior["bundle_hash"],
                    previous_id=prior["id"], previous_hash=prior["hash"], provider=provider,
                    event_id=event, observed_at=observed.isoformat(), scope=scope,
                    source_receipt_sha256=source, release=release,
                    report="OWNER_REPORTED_LIVE_PROBE_NOT_INDEPENDENTLY_VERIFIED")
        return _insert(db, app_id, identity, experiment_id, data["proposal_hash"],
                       data["bundle_hash"], "PROBE_OBSERVED", data, prior["id"], now())


def _actions(state):
    if state is None:
        return ["Generate the browser integration package from the current tracking proposal"]
    if state == "DOWNLOADED":
        return ["Integrate the exact files through your app repository workflow",
                "Report installation with the current release and an exact reference",
                "Then record a live provider probe"]
    if state == "REPORTED_INSTALLED":
        return ["Verify consent, identity and provider events in your own app",
                "Record a live probe identity, time and scope"]
    return ["Keep the probe receipt; provider delivery and business outcomes remain separate"]


def readout(store, app_id, experiment_id=None):
    """Return bounded lifecycle state per experiment; never infer a later stage."""
    store.app(app_id)
    with connection(store.path) as db:
        if experiment_id is None:
            rows = [decoded(row) for row in db.execute(
                "SELECT * FROM instrumentation_receipts WHERE app_id=? ORDER BY created DESC,id LIMIT 200",
                (app_id,))]
        else:
            rows = [decoded(row) for row in db.execute(
                "SELECT * FROM instrumentation_receipts WHERE app_id=? AND experiment_id=? ORDER BY created DESC,id LIMIT 200",
                (app_id, experiment_id))]
    grouped = {}
    for row in rows:
        grouped.setdefault(row["experiment_id"], []).append(row)
    result = []
    for identity, items in grouped.items():
        items.sort(key=lambda item: (item["created"], item["id"]))
        by_state = {}
        for item in items:
            by_state[item["state"]] = item
        latest = items[-1]
        states = []
        for state in ("DOWNLOADED", "REPORTED_INSTALLED", "PROBE_OBSERVED"):
            item = by_state.get(state)
            states.append(dict(state=state, observed=item is not None,
                               at=item["created"] if item else None,
                               receipt_id=item["id"] if item else None,
                               receipt_hash=item["hash"] if item else None))
        result.append(dict(experiment_id=identity, latest_state=latest["state"],
                           proposal_hash=latest["proposal_hash"], bundle_hash=latest["bundle_hash"],
                           states=states, receipts=[dict(state=item["state"], id=item["id"],
                                                         hash=item["hash"], created=item["created"],
                                                         **{key: value for key, value in item["data"].items()
                                                            if key in ("release", "install_reference", "provider",
                                                                       "event_id", "observed_at", "scope",
                                                                       "source_receipt_sha256", "reported_at")})
                                     for item in items],
                           next_actions=_actions(latest["state"]),
                           boundary="Download is not installation; attestation is not verified delivery; a probe is owner-reported."))
    return sorted(result, key=lambda item: item["experiment_id"])
