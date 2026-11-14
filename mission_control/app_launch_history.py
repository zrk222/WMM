"""Retain app-scoped launch observations in the existing audit ledger."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from .app_launch_status import ConnectRead, StorefrontRead, fresh, resolve
from .common import Invalid, canonical, digest, iso_time, now
from .db import connection

ACTION = "app.launch_status.observed"
DECLARATION = "app.launch_status.declared"
DECLARABLE = ("NOT_SUBMITTED", "IN_REVIEW", "LIVE", "REMOVED", "UNKNOWN")


@dataclass(frozen=True)
class Sources:
    connect: ConnectRead | None
    storefronts: list[StorefrontRead]
    store_app_id: str | None = None
    source_hashes: tuple[str, ...] = ()


def _history(db: Any, app_id: str, version: int | None, limit: int, action: str = ACTION) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT detail FROM audit WHERE app_id=? AND action=? AND "
        "(? IS NULL OR json_extract(detail,'$.app_version')=?) ORDER BY id DESC LIMIT ?",
        (app_id, action, version, version, limit),
    )
    result = []
    for row in rows:
        try:
            data = json.loads(row["detail"])
        except (TypeError, ValueError):
            raise Invalid("Saved launch evidence failed its integrity check") from None
        if not isinstance(data, dict):
            raise Invalid("Saved launch evidence failed its integrity check")
        fingerprint = data.pop("evidence_hash", None)
        if data.get("app_id") != app_id or digest(data) != fingerprint:
            raise Invalid("Saved launch evidence failed its integrity check")
        result.append(dict(data, evidence_hash=fingerprint))
    return result


def retain(path: Path, app_id: str, app_version: int, sources: Sources) -> dict[str, Any]:
    """Append identity-checked source facts, with current app-version protection."""
    with connection(path, write=True) as db:
        return retain_in_snapshot(db, app_id, app_version, sources)


def retain_in_snapshot(db: Any, app_id: str, app_version: int, sources: Sources) -> dict[str, Any]:
    """Append in an existing writer transaction so a job and its evidence commit together."""
    observed_at = now()
    clock = iso_time(observed_at)
    stamps = [row["observed_at"] for row in sources.storefronts]
    if sources.connect:
        stamps.append(sources.connect["observed_at"])
    if not stamps or any(iso_time(stamp) > clock for stamp in stamps):
        raise Invalid("Launch status needs source observations dated no later than now")
    readings = dict(
        connect=sources.connect,
        store_app_id=sources.store_app_id,
        source_hashes=list(sources.source_hashes),
        storefronts=sorted(
            sources.storefronts, key=lambda row: (row["storefront"], iso_time(row["observed_at"]), row["state"])
        ),
    )
    app = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None or type(app_version) is not int or app["version"] != app_version:
        raise Invalid("Launch observations require the current app version")
    previous = _history(db, app_id, None, 1)
    if previous and previous[0]["readings"].get("store_app_id") != sources.store_app_id:
        previous = []
    if previous and previous[0]["app_version"] == app_version and previous[0]["readings"] == readings:
        return previous[0]
    verified_live = bool(previous and (previous[0]["status"] == "LIVE" or previous[0]["previous_verified_live"]))
    status = resolve(
        sources.connect,
        sources.storefronts,
        clock,
        previous_verified_live=verified_live,
    )
    payload = dict(
        status,
        app_id=app_id,
        app_version=app_version,
        readings=readings,
        previous_status=previous[0]["status"] if previous else "UNKNOWN",
        previous_verified_live=verified_live,
    )
    receipt = dict(payload, evidence_hash=digest(payload))
    db.execute(
        "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
        (app_id, ACTION, canonical(receipt), observed_at),
    )
    return receipt


def retain_job_result(db: Any, job: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Validate the leased Apple read against the current saved provider binding."""
    app_id = job["app_id"]
    request = job["data"]
    version = request["manifest_version"]
    app = db.execute("SELECT data,version FROM apps WHERE id=?", (app_id,)).fetchone()
    record = db.execute(
        "SELECT data,version FROM records WHERE app_id=? AND id=? AND kind='connection'",
        (app_id, request.get("connection_id")),
    ).fetchone()
    store_id = report.get("store_app_id")
    if (
        app is None
        or type(version) is not int
        or version != app["version"]
        or record is None
        or type(request.get("connection_version")) is not int
        or record["version"] != request.get("connection_version")
        or report.get("app_id") != app_id
        or report.get("provider") != "app_store"
        or report.get("request") != request["options"]
        or str(json.loads(app["data"]).get("store_app_id")) != store_id
        or json.loads(record["data"]).get("store_app_id") != store_id
        or json.loads(record["data"]).get("provider") != "app_store"
    ):
        raise Invalid("The Apple launch read no longer matches this app or connection")
    public = report.get("storefront_read")
    hashes = [report.get("source_hash")]
    if public is not None:
        if not isinstance(public, dict) or public.get("storefront") != request["options"].get("storefront"):
            raise Invalid("The Apple launch read did not confirm the selected storefront")
        hashes.append(report.get("storefront_source_hash"))
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes):
        raise Invalid("Apple launch source evidence fingerprint is missing")
    connect: ConnectRead = {
        "observed_at": report["observed_at"],
        "complete": report["complete"],
        "states": report["states"],
    }
    storefronts = [cast(StorefrontRead, public)] if public is not None else []
    fingerprints = tuple(value for value in hashes if isinstance(value, str))
    return retain_in_snapshot(db, app_id, version, Sources(connect, storefronts, store_id, fingerprints))


def declare(path: Path, app_id: str, principal: str, body: Any, *, commit_check: Callable[[], Any]) -> dict[str, Any]:
    """Retain a local declaration without changing any verified eligibility."""
    from .review_access import member

    if (
        not isinstance(body, dict)
        or set(body) != {"app_version", "status"}
        or type(body["app_version"]) is not int
        or body["status"] not in DECLARABLE
    ):
        raise Invalid("Select a launch status for the current app")
    version = body["app_version"]
    status = body["status"]
    with connection(path, write=True) as db:
        member(db, app_id, principal, "OWNER")
        app = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
        if app is None or app["version"] != version:
            raise Invalid("The app changed. Reopen it before saving launch status.")
        previous = _history(db, app_id, version, 1, DECLARATION)
        commit_check()
        if previous and previous[0]["status"] == status and previous[0]["declared_by"] == principal:
            return previous[0]
        stamp = now()
        payload = dict(
            app_id=app_id,
            app_version=version,
            status=status,
            source="OWNER_DECLARED",
            observed_at=stamp,
            declared_by=principal,
            verified=False,
            storefronts=[],
            previous_status=previous[0]["status"] if previous else "UNKNOWN",
        )
        record = dict(payload, evidence_hash=digest(payload))
        db.execute(
            "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
            (app_id, DECLARATION, canonical(record), stamp),
        )
        return record


def current(path: Path, app_id: str, app_version: int, clock: datetime) -> dict[str, Any]:
    """Project current status without deleting historical observations."""
    with connection(path) as db:
        app = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
        if app is None or app["version"] != app_version:
            raise Invalid("Launch status requires the current app version")
        latest = _history(db, app_id, app_version, 1)
        declarations = _history(db, app_id, app_version, 1, DECLARATION)
    declaration = (
        {key: value for key, value in declarations[0].items() if key != "declared_by"} if declarations else None
    )
    if not latest:
        return dict(resolve(None, [], clock), owner_declaration=declaration)
    record = latest[0]
    readings = record["readings"]
    current_status = resolve(
        readings["connect"],
        readings["storefronts"],
        clock,
        previous_verified_live=record["previous_verified_live"],
    )
    return dict(
        current_status,
        last_observation=record,
        owner_declaration=declaration,
        stale=(
            not fresh(record["observed_at"], clock)
            or record["status"] != current_status["status"]
            or record["verified_storefronts"] != current_status["verified_storefronts"]
        ),
    )


def history(path: Path, app_id: str, app_version: int) -> list[dict[str, Any]]:
    """Return bounded history for the app and version selected by the caller."""
    with connection(path) as db:
        return _history(db, app_id, app_version, 100)
