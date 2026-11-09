"""Map an MMP CSV/JSON export into a validated install-attribution batch plus checklist."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import uuid

from .common import Invalid, digest
from .install_attribution import validate_batch

MAPPING_FIELDS = {"install_id", "state", "occurred_at"}


def _mapping(value):
    if not isinstance(value, dict) or not MAPPING_FIELDS <= set(value) or set(value) - MAPPING_FIELDS - {"state_values"}:
        raise Invalid("Mapping must name install_id, state and occurred_at columns")
    for key in MAPPING_FIELDS:
        if not isinstance(value[key], str) or not value[key]:
            raise Invalid("Mapping columns must be nonempty names")
    states = value.get("state_values", {})
    if not isinstance(states, dict) or any(
            not isinstance(key, str) or not isinstance(mapped, str) for key, mapped in states.items()):
        raise Invalid("state_values must map raw values to state names")
    return value


def parse_text(text, fmt):
    """Parse a bounded uploaded CSV/JSON export without touching the filesystem."""
    if fmt == "json":
        value = json.loads(text)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise Invalid("JSON input must be a list of objects")
        return value
    if fmt == "csv":
        return list(csv.DictReader(text.splitlines()))
    raise Invalid("Choose csv or json input")


def load_rows(path, fmt):
    """Read a local export file; the HTTP import path uses parse_text directly."""
    return parse_text(Path(path).read_text(encoding="utf-8"), fmt)


def map_rows(rows, mapping, source, campaign_token, observed_at, window, coverage, request_id=None,
             source_receipt_sha256=None, columns=None):
    """Produce one batch and a coverage checklist; never write or infer missing values."""
    mapping = _mapping(mapping)
    request_id = request_id or str(uuid.uuid4())
    derived_receipt = source_receipt_sha256 is None
    source_receipt_sha256 = source_receipt_sha256 or digest({"rows": rows})
    rejected, installed = [], []
    seen = {}
    conflicts = []
    duplicates = []
    counts = {}
    for index, row in enumerate(rows, start=1):
        values = {}
        for field in MAPPING_FIELDS:
            raw = row.get(mapping[field])
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                rejected.append({"row": index, "reason": field + " is missing"})
                break
            values[field] = raw.strip() if isinstance(raw, str) else raw
        if len(values) != len(MAPPING_FIELDS):
            continue
        state = mapping.get("state_values", {}).get(values["state"], values["state"])
        item = dict(install_id=values["install_id"], state=state, occurred_at=values["occurred_at"])
        prior = seen.get(item["install_id"])
        if prior is not None:
            if prior == item:
                duplicates.append(item["install_id"])
            else:
                conflicts.append(item["install_id"])
            continue
        seen[item["install_id"]] = item
        installed.append(item)
        counts[state] = counts.get(state, 0) + 1
    columns = list(columns or (rows[0].keys() if rows else []))
    used = set(mapping[field] for field in MAPPING_FIELDS)
    unmapped = [name for name in columns if name not in used]
    coverage = dict(coverage, excluded=dict(coverage.get("excluded", {})))
    if duplicates:
        coverage["excluded"]["DUPLICATE"] = len(duplicates)
    batch = dict(source=source, campaign_token=campaign_token, request_id=request_id,
                 source_receipt_sha256=source_receipt_sha256, observed_at=observed_at,
                 window=window, coverage=coverage, installs=installed)
    checklist = dict(schema="wmm.install-import-checklist.v1", status="READY",
                     rows_read=len(rows), rows_emitted=len(installed),
                     counts=counts, duplicates=duplicates[:50], conflicts=conflicts[:50],
                     rejected=rejected[:50], unmapped_columns=unmapped,
                     request_id=request_id, source_receipt_sha256=source_receipt_sha256)
    if rejected:
        checklist["status"] = "BLOCKED"
        checklist["reason"] = "Rows with missing required values"
    if conflicts:
        checklist["status"] = "BLOCKED"
        checklist["reason"] = "Conflicting duplicate install identities"
    if not rows:
        checklist["status"] = "BLOCKED"
        checklist["reason"] = "No rows were read"
    if derived_receipt:
        checklist.setdefault("warnings", []).append("Source receipt hash was derived from input rows; supply the original receipt for audit.")
    if not coverage.get("complete"):
        checklist.setdefault("warnings", []).append("Coverage is incomplete; counts may be null or partial")
    if checklist["status"] == "READY":
        try:
            checklist["_batch"] = validate_batch(batch)
        except Invalid as exc:
            checklist["status"] = "BLOCKED"
            checklist["reason"] = str(exc)
    return batch, checklist


def main(argv=None):
    parser = argparse.ArgumentParser(description="Map an MMP install export to a WMM batch")
    parser.add_argument("--input", required=True)
    parser.add_argument("--input-format", choices=("csv", "json"), required=True)
    parser.add_argument("--mapping", required=True, help="JSON mapping file")
    parser.add_argument("--source", required=True)
    parser.add_argument("--campaign-token", required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--source-receipt-sha256")
    parser.add_argument("--source-receipt-file")
    parser.add_argument("--coverage-complete", action="store_true")
    parser.add_argument("--source-event-count", type=int)
    parser.add_argument("--out", required=True)
    parser.add_argument("--checklist")
    args = parser.parse_args(argv)
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    rows = load_rows(args.input, args.input_format)
    digest_value = args.source_receipt_sha256
    if args.source_receipt_file:
        digest_value = hashlib.sha256(Path(args.source_receipt_file).read_bytes()).hexdigest()
    coverage = dict(complete=args.coverage_complete, source_event_count=args.source_event_count)
    batch, checklist = map_rows(rows, mapping, args.source, args.campaign_token, args.observed_at,
                                dict(starts_at=args.window_start, ends_at=args.window_end), coverage, args.request_id, digest_value,
                                columns=list(rows[0].keys()) if rows else [])
    payload = (json.dumps(checklist.pop("_batch", batch), indent=2) if checklist["status"] == "READY" else json.dumps({"status": "BLOCKED", "reason": checklist.get("reason")}, indent=2)) + "\n"
    if args.out == "-":
        sys.stdout.write(payload)
    else:
        Path(args.out).write_text(payload, encoding="utf-8")
    if args.checklist:
        Path(args.checklist).write_text(json.dumps(checklist, indent=2) + "\n", encoding="utf-8")
    sys.stderr.write(json.dumps({key: checklist[key] for key in ("status", "rows_read", "rows_emitted", "counts")}) + "\n")
    return 0 if checklist["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())



