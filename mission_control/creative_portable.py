"""Portable analysis/brief history; hash integrity never authenticates authorship."""

import json
from .common import Invalid, canonical, digest, iso_time, safe_data
from .creative_analysis import analysis_data, saved_items, decoded
from .creative_briefs import definition, compose, record_scope, checked
from .creative_library import reference_data


def export_production(db, app_id):
    """Export immutable source/brief versions, excluding derived freshness states."""
    return {
        "analyses": saved_items(db, "creative_analyses", app_id),
        "briefs": saved_items(db, "creative_briefs", app_id),
    }


def history_rows(items, app_id):
    """Validate exact grouped envelopes, bounded revisions and contiguous versions."""
    if not isinstance(items, list) or len(items) > 1000:
        raise Invalid("Portable production history allows at most 1000 items")
    output = []
    seen = set()
    for item in items:
        rows = history_item(item, seen)
        for version, row in enumerate(rows, 1):
            validate_row(row, app_id, item["id"], version)
        output.extend(rows)
        seen.add(item["id"])
    if len(output) > 5000:
        raise Invalid("Portable production history allows at most 5000 revisions")
    return output


def history_item(item, seen):
    """Validate one grouped current pointer before replaying its versions."""
    if not isinstance(item, dict) or set(item) != {"id", "versions", "current"} or item["id"] in seen:
        raise Invalid("Invalid or duplicate portable production identity")
    rows = item["versions"]
    if not isinstance(rows, list) or not rows or rows[-1] != item["current"]:
        raise Invalid("Portable production current version changed")
    return rows


def validate_row(row, app_id, item_id, version):
    """Require exact scope, version, finite bytes and monotonically replayable identity."""
    if not isinstance(row, dict) or set(row) != {"app_id", "id", "version", "data", "hash", "created"}:
        raise Invalid("Invalid portable production row")
    if row["app_id"] != app_id or row["id"] != item_id or type(row["version"]) is not int or row["version"] != version:
        raise Invalid("Production history scope or version changed")
    safe_data(row["data"])
    iso_time(row["created"])
    if digest(row["data"]) != row["hash"]:
        raise Invalid("Production history hash changed")


def captured_source(db, app_id, reference_id, value_hash, version=None):
    """Resolve an actual retained historical capture, never an arbitrary envelope."""
    row = db.execute(
        "SELECT * FROM creative_captures WHERE app_id=? AND reference_id=? AND hash=? AND (? IS NULL OR version=?)",
        (app_id, reference_id, value_hash, version, version),
    ).fetchone()
    if not row:
        raise Invalid("Analysis source capture is absent from this workspace")
    return decoded(row)


def restore_analysis(db, app_id, rows):
    """Replay inspected analysis versions against their actual source captures."""
    identities = {}
    references = {}
    for row in rows:
        data = row["data"]
        source = captured_source(db, app_id, data.get("reference_id"), data.get("capture_hash"))
        if analysis_data(data, source) != data:
            raise Invalid("Portable analysis is not normalized")
        reference = data["reference_id"]
        if identities.get(row["id"], reference) != reference or references.get(reference, row["id"]) != row["id"]:
            raise Invalid("Analysis reference identity changed or duplicated")
        identities[row["id"]] = reference
        references[reference] = row["id"]
        insert(db, "creative_analyses", row)


def brief_data(db, app_id, data, stamp=None):
    """Validate frozen historic evidence and deterministic original copy without approving it."""
    fields = {
        "definition",
        "app",
        "app_hash",
        "analysis",
        "source",
        "records",
        "content",
        "state",
        "render",
        "publication",
    }
    if set(data) not in (fields, fields | {"production"}, fields | {"production", "discovery"}) or (
        data["state"],
        data["render"],
        data["publication"],
    ) != ("PREPARED", "NOT_RUN", "NOT_RUN"):
        raise Invalid("Invalid portable preparation state")
    d = definition(data["definition"])
    if digest(data["app"]) != data["app_hash"]:
        raise Invalid("Frozen app manifest changed")
    row = db.execute(
        "SELECT * FROM creative_analyses WHERE app_id=? AND id=? AND hash=?",
        (app_id, d["analysis_id"], d["analysis_hash"]),
    ).fetchone()
    if not row or decoded(row) != data["analysis"]:
        raise Invalid("Brief analysis is absent or changed")
    a = data["analysis"]["data"]
    source = captured_source(db, app_id, a["reference_id"], a["capture_hash"], data["source"]["version"])
    if source != data["source"] or reference_data(source["data"]) != source["data"]:
        raise Invalid("Brief source changed")
    frozen_records(data, d, app_id)
    if "production" in data:
        from .production_portable import validate_frozen

        validate_frozen(db, app_id, data["production"], data["app_hash"], source, d["channel"], stamp)
    if ("discovery" in data) != ("discovery" in d):
        raise Invalid("Discovery binding and frozen proof differ")
    validate_frozen_records(data, stamp)
    if "discovery" in data:
        validate_research(data, app_id, stamp)
    if compose(data) != data["content"]:
        raise Invalid("Original brief content changed from its frozen proof")


def validate_research(data, app_id, stamp):
    """Validate historic frozen research, never restore it as current authorization."""
    try:
        _validate_research(data, app_id, stamp)
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise Invalid("Invalid frozen research proof") from exc


def validate_frozen_records(data, stamp):
    """Validate historic product metadata at preparation time, not present-day bytes."""
    if stamp is None:
        raise Invalid("Brief creation time is required")
    try:
        for row in data["records"]:
            kind = row["kind"]
            value = row["data"]
            record_scope(value, kind, data["app"])
            if kind == "asset":
                if value.get("authentic") is not True or value.get("rights_cleared") is not True:
                    raise Invalid("Frozen app asset authenticity or rights missing")
            else:
                checked(value, kind, stamp)
    except (KeyError, TypeError, ValueError) as exc:
        raise Invalid("Invalid frozen product evidence") from exc


def _validate_research(data, app_id, stamp):
    from .discovery_contract import query, review as review_contract
    from .discovery_query import evaluate, boundaries
    from .discovery_store import scoped

    proof = data["discovery"]
    request = data["definition"]["discovery"]
    source = data["source"]
    fields = {
        "schema",
        "mode",
        "manifest_version",
        "app_hash",
        "collection_id",
        "collection_version",
        "collection_hash",
        "collection_provenance",
        "reference_id",
        "source_version",
        "source_hash",
        "review_id",
        "review_version",
        "review_hash",
        "card",
        "collection",
        "review",
        "authentic_proofs",
        "policy",
        "boundaries",
        "foreign_bytes",
    }
    if not isinstance(proof, dict) or set(proof) != fields or proof["schema"] != "wmm.brief-research-proof.v1":
        raise Invalid("Invalid frozen research shape")
    collection = proof["collection"]
    review = proof["review"]
    if len(canonical(collection).encode("utf-8")) > 1048576:
        raise Invalid("Research collection exceeds the 1 MiB brief evidence limit")
    for doc, kind in ((collection, "COLLECTION"), (review, "REVIEW")):
        if (
            not isinstance(doc, dict)
            or set(doc) != {"app_id", "id", "version", "kind", "data", "hash", "created"}
            or doc["app_id"] != app_id
            or doc["kind"] != kind
            or type(doc["version"]) is not int
            or doc["version"] < 1
            or digest(doc["data"]) != doc["hash"]
        ):
            raise Invalid("Frozen research document integrity changed")
        iso_time(doc["created"])
    if (proof["mode"], proof["manifest_version"], proof["app_hash"]) != (
        request["mode"],
        request["manifest_version"],
        data["app_hash"],
    ):
        raise Invalid("Frozen research app or mode changed")
    if (proof["collection_id"], proof["collection_version"], proof["collection_hash"]) != (
        collection["id"],
        collection["version"],
        collection["hash"],
    ) or (request["collection_id"], request["collection_hash"]) != (collection["id"], collection["hash"]):
        raise Invalid("Frozen collection identity changed")
    if (proof["review_id"], proof["review_version"], proof["review_hash"]) != (
        review["id"],
        review["version"],
        review["hash"],
    ) or request["review_hash"] != review["hash"]:
        raise Invalid("Frozen review identity changed")
    if (proof["reference_id"], proof["source_version"], proof["source_hash"]) != (
        source["reference_id"],
        source["version"],
        source["hash"],
    ) or request["reference_id"] != source["reference_id"]:
        raise Invalid("Frozen research source changed")
    if proof["boundaries"] != boundaries() or proof["foreign_bytes"] != "NOT_AUTHORIZED":
        raise Invalid("Research cannot authorize execution or foreign bytes")
    cd = collection["data"]
    rd = review["data"]
    app = dict(version=proof["manifest_version"], hash=data["app_hash"])
    if cd["manifest_version"] != app["version"] or cd["app_hash"] != app["hash"] or cd["state"] != "OBSERVED":
        raise Invalid("Frozen collection app or state changed")
    if proof["collection_provenance"] != cd.get("collection_provenance", "NOT_INDEPENDENTLY_VERIFIED"):
        raise Invalid("Collection provenance changed")
    if query(cd["query"]) != cd["query"] or review_contract(rd["review"]) != rd["review"]:
        raise Invalid("Frozen research content is invalid")
    if rd["reference_id"] != source["reference_id"]:
        raise Invalid("Frozen review source changed")
    value = scoped(app, source, review, stamp)
    if value is None or value["card"] != proof["card"]:
        raise Invalid("Frozen review scope or card changed")
    selected = [r for r in cd["results"] if r["reference_id"] == source["reference_id"]]
    if len(selected) != 1:
        raise Invalid("Frozen selected research card is missing")
    row = selected[0]
    if (
        row["source_hash"] != source["hash"]
        or row["source_version"] != source["version"]
        or row["review"] != dict(id=review["id"], version=review["version"], hash=review["hash"])
    ):
        raise Invalid("Frozen selection identity changed")
    if row["included"] is not True or row["qualified"] is not True or row["policy"] != proof["policy"]:
        raise Invalid("Frozen research was not qualified and included")
    historic = evaluate(source, value, cd["query"], cd["observed_at"])
    if historic["included"] is not True or historic["qualified"] is not True or historic["policy"] != proof["policy"]:
        raise Invalid("Frozen research qualification changed")
    if stamp is None:
        raise Invalid("Brief creation time is required")
    current = evaluate(source, value, cd["query"], stamp)
    if current["included"] is not True or current["qualified"] is not True:
        raise Invalid("Research was stale when brief was prepared")
    for observed in (cd["observed_at"], source["data"]["metric_at"]):
        if not 0 <= (iso_time(stamp) - iso_time(observed)).total_seconds() <= 86400:
            raise Invalid("Research was stale when brief was prepared")
    if value["card"]["rights_status"] == "REVOKED" or (proof["mode"] == "LICENSED_EDIT" and current["rights_missing"]):
        raise Invalid("Frozen source rights do not support this mode")
    ids = value["card"]["authentic_evidence_ids"]
    records = {r["id"]: r for r in data["records"] if r["kind"] == "asset"}
    if not ids or not set(ids).issubset(records):
        raise Invalid("Frozen authentic app assets are missing")
    expected = []
    for identity in ids:
        record = records[identity]
        if record["data"].get("authentic") is not True or record["data"].get("rights_cleared") is not True:
            raise Invalid("Frozen app asset authenticity or rights missing")
        expected.append(dict(id=identity, version=record["version"], hash=record["hash"]))
    if proof["authentic_proofs"] != expected:
        raise Invalid("Frozen authentic app proof changed")


def frozen_records(data, d, app_id):
    """Validate every selected frozen record hash and its explicit proof identity."""
    rows = data["records"]
    if not isinstance(rows, list) or len(rows) != 3 + len(d["claim_ids"]) + len(d["asset_ids"]):
        raise Invalid("Frozen production evidence is incomplete")
    expected = {d[k + "_id"]: k for k in ("readiness", "store", "route")}
    expected.update({item: "claim" for item in d["claim_ids"]})
    expected.update({item: "asset" for item in d["asset_ids"]})
    if len(expected) != len(rows) or len({r.get("id") for r in rows}) != len(rows):
        raise Invalid("Duplicate production evidence identity")
    for row in rows:
        if (
            row.get("app_id") != app_id
            or expected.get(row.get("id")) != row.get("kind")
            or digest({"kind": row["kind"], "data": row["data"], "source": row["source"]}) != row.get("hash")
        ):
            raise Invalid("Frozen production evidence scope or hash changed")


def insert(db, table, row):
    """Insert validated immutable history inside the caller's snapshot transaction."""
    if table not in ("creative_analyses", "creative_briefs"):
        raise Invalid("Unknown production history")
    db.execute(
        f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",
        (row["app_id"], row["id"], row["version"], canonical(row["data"]), row["hash"], row["created"]),
    )


def restore_production(db, app_id, payload):
    """Restore all source and brief history atomically; old snapshots remain valid."""
    if payload is None:
        return
    if not isinstance(payload, dict) or set(payload) != {"analyses", "briefs"}:
        raise Invalid("Invalid portable production schema")
    analyses = history_rows(payload["analyses"], app_id)
    briefs = history_rows(payload["briefs"], app_id)
    restore_analysis(db, app_id, analyses)
    for row in briefs:
        brief_data(db, app_id, row["data"], row["created"])
        insert(db, "creative_briefs", row)
