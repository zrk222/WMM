"""Durable browser-instrumentation lifecycle; downloads and attestations are not delivery."""
import json
import re
from datetime import datetime, timezone

from .common import Invalid, canonical, digest, iso_time, now, required
from .db import connection
from .review_access import member

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


def _checked_receipt(row):
    value = decoded(row)
    if digest(value["data"]) != value["hash"]:
        raise Invalid("Saved instrumentation receipt integrity changed")
    return value


def _current_download(db, app_id, experiment_id):
    row = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND experiment_id=? "
                     "AND state='DOWNLOADED' ORDER BY created DESC,id DESC LIMIT 1",
                     (app_id, experiment_id)).fetchone()
    return _checked_receipt(row) if row is not None else None


def _latest_attestation(db, previous, state, release):
    row = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND experiment_id=? "
                     "AND state=? AND previous_id=? AND json_extract(data,'$.previous_hash')=? "
                     "AND json_type(data,'$.owner_attestation')='object' AND json_extract(data,'$.release')=? "
                     "ORDER BY created DESC,id DESC LIMIT 1",
                     (previous["app_id"], previous["experiment_id"], state, previous["id"],
                      previous["hash"], release)).fetchone()
    return _checked_receipt(row) if row is not None else None


def _prior(db, app_id, experiment_id, identity, value_hash, state):
    row = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=? AND experiment_id=?",
                     (app_id, identity, experiment_id)).fetchone()
    if row is None or row["state"] != state or row["hash"] != value_hash:
        raise Invalid("Select this app's exact previous instrumentation receipt")
    return _checked_receipt(row)


def _owner_for_release(db, app_id, user, release):
    owner = member(db, app_id, user["principal"], "OWNER")
    app = db.execute("SELECT data FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None or release != json.loads(app["data"]).get("release"):
        raise Invalid("Select the current app release before reporting instrumentation")
    return owner


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


def record_installed(store, app_id, experiment_id, body, *, user):
    """Append an owner-reported installation attestation for the exact downloaded bundle."""
    _exact(body, {"proposal_hash", "downloaded_id", "downloaded_hash", "release", "install_reference", "reported_at"})
    release = _text(body["release"], "Release", 100)
    reference = _text(body["install_reference"], "Installation reference", 200)
    reported = _time(body["reported_at"], "Reported time")
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        owner = _owner_for_release(db, app_id, user, release)
        prior = _prior(db, app_id, experiment_id, body["downloaded_id"], body["downloaded_hash"], "DOWNLOADED")
        if prior["data"]["proposal_hash"] != body["proposal_hash"]:
            raise Invalid("Installation does not match this downloaded proposal")
        if _current_download(db, app_id, experiment_id)["id"] != prior["id"]:
            raise Invalid("Report installation for the most recently downloaded bundle")
        if reported < iso_time(prior["created"]):
            raise Invalid("Reported time cannot precede the download")
        identity = digest(["REPORTED_INSTALLED", prior["id"], owner["principal"], release, reference, reported.isoformat()])
        saved = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=?",
                           (app_id, identity)).fetchone()
        if saved:
            return decoded(saved)
        data = dict(state="REPORTED_INSTALLED", experiment_id=experiment_id,
                    proposal_hash=body["proposal_hash"], bundle_hash=prior["bundle_hash"],
                    previous_id=prior["id"], previous_hash=prior["hash"], release=release,
                    install_reference=reference, reported_at=reported.isoformat(),
                    owner_attestation=dict(principal=owner["principal"], role_version=owner["version"]),
                    report="OWNER_ATTESTED_NOT_VERIFIED_DELIVERY")
        return _insert(db, app_id, identity, experiment_id, body["proposal_hash"],
                       prior["bundle_hash"], "REPORTED_INSTALLED", data, prior["id"], now())


def record_probe(store, app_id, experiment_id, body, *, user):
    """Append one owner-reported live probe with exact identity, time and scope."""
    _exact(body, {"previous_id", "previous_hash", "provider", "event_id", "observed_at",
                  "scope", "source_receipt_sha256", "release"})
    release = _text(body["release"], "Release", 100)
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
        owner = _owner_for_release(db, app_id, user, release)
        prior = _prior(db, app_id, experiment_id, body["previous_id"], body["previous_hash"], "REPORTED_INSTALLED")
        if not prior["data"].get("owner_attestation") or prior["data"]["release"] != release:
            raise Invalid("Report installation for this release as the verified app owner before saving a probe")
        download = _current_download(db, app_id, experiment_id)
        current = _latest_attestation(db, download, "REPORTED_INSTALLED", release) if download else None
        if current is None or current["id"] != prior["id"]:
            raise Invalid("Record a probe for the current bundle and installation receipt")
        if observed < iso_time(prior["data"]["reported_at"]):
            raise Invalid("Probe time cannot precede the installation report")
        identity = digest(["PROBE_OBSERVED", prior["id"], owner["principal"], release, provider, event, observed.isoformat(), scope, source])
        saved = db.execute("SELECT * FROM instrumentation_receipts WHERE app_id=? AND id=?",
                           (app_id, identity)).fetchone()
        if saved:
            return decoded(saved)
        data = dict(state="PROBE_OBSERVED", experiment_id=experiment_id,
                    proposal_hash=prior["data"]["proposal_hash"], bundle_hash=prior["bundle_hash"],
                    previous_id=prior["id"], previous_hash=prior["hash"], provider=provider,
                    event_id=event, observed_at=observed.isoformat(), scope=scope,
                    source_receipt_sha256=source, release=release,
                    owner_attestation=dict(principal=owner["principal"], role_version=owner["version"]),
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
    scope = "app_id=?" if experiment_id is None else "app_id=? AND experiment_id=?"
    params = (app_id,) if experiment_id is None else (app_id, experiment_id)
    with connection(store.path) as db:
        db.execute("BEGIN")
        app = db.execute("SELECT data FROM apps WHERE id=?", (app_id,)).fetchone()
        if app is None:
            raise Invalid("Select an existing app")
        release = json.loads(app["data"]).get("release")
        groups = db.execute(
            "SELECT experiment_id, sum(CASE WHEN state!='DOWNLOADED' "
            "AND json_type(data,'$.owner_attestation') IS NULL THEN 1 ELSE 0 END) AS legacy "
            "FROM instrumentation_receipts WHERE " + scope
            + " GROUP BY experiment_id ORDER BY max(created) DESC,experiment_id LIMIT 200", params
        ).fetchall()
        chains = []
        for group in groups:
            identity = group["experiment_id"]
            download = _current_download(db, app_id, identity)
            installed = _latest_attestation(db, download, "REPORTED_INSTALLED", release) if download else None
            probe = _latest_attestation(db, installed, "PROBE_OBSERVED", release) if installed else None
            chains.append((identity, [item for item in (download, installed, probe) if item], group["legacy"]))
    result = []
    for identity, current, legacy in chains:
        latest = current[-1] if current else None
        by_state = {item["state"]: item for item in current}
        states = []
        for state in ("DOWNLOADED", "REPORTED_INSTALLED", "PROBE_OBSERVED"):
            item = by_state.get(state)
            states.append(dict(state=state, observed=item is not None,
                               at=item["created"] if item else None,
                               receipt_id=item["id"] if item else None,
                               receipt_hash=item["hash"] if item else None))
        result.append(dict(experiment_id=identity, latest_state=latest["state"] if latest else None,
                           proposal_hash=latest["proposal_hash"] if latest else None,
                           bundle_hash=latest["bundle_hash"] if latest else None,
                           states=states, receipts=[dict(state=item["state"], id=item["id"],
                                                         hash=item["hash"], created=item["created"],
                                                         **{key: value for key, value in item["data"].items()
                                                            if key in ("release", "install_reference", "provider",
                                                                       "event_id", "observed_at", "scope",
                                                                       "source_receipt_sha256", "reported_at")})
                                     for item in current],
                           legacy_unverified_receipts=legacy,
                           next_actions=_actions(latest["state"] if latest else None),
                           boundary="Download is not installation; attestation is not verified delivery; a probe is owner-reported."))
    return sorted(result, key=lambda item: item["experiment_id"])
