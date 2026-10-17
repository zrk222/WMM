"""Read-only ASA/AEO worksheet. Supplied data is not independently verified."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


def obj(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def items(value, name):
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def number(value, name, lower=0, upper=None, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or value < lower or (upper is not None and value > upper):
        raise ValueError(f"{name} outside allowed bounds")
    if integer and not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def timestamp(value, name):
    try:
        parsed = datetime.fromisoformat(text(value, name).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include timezone")
    return parsed


def public_url(value):
    parsed = urlparse(value) if isinstance(value, str) else None
    return bool(parsed and parsed.scheme == "https" and parsed.hostname
                and not parsed.username and not parsed.password)


def wilson_lower(successes, trials):
    if trials == 0:
        return None
    z = 1.96
    p = successes / trials
    a = z * z / trials
    return max(0.0, (p + a / 2 - z * math.sqrt(p * (1 - p) / trials + a / (4 * trials))) / (1 + a))


def asa_analysis(data, app_id):
    data = obj(data, "asa")
    if data.get("app_id") != app_id:
        raise ValueError("asa app scope mismatch")
    taps = number(data.get("taps"), "taps", integer=True)
    paid = number(data.get("paid"), "paid", upper=taps, integer=True)
    for field in ("mature", "counts_verified", "contribution_verified"):
        if not isinstance(data.get(field), bool):
            raise ValueError(f"asa.{field} must be boolean")
    currency = text(data.get("currency"), "currency")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency must be an uppercase currency code")
    for field in ("cohort_id", "contribution_horizon", "source_ref"):
        text(data.get(field), field)
    contribution = number(data.get("contribution_per_payer_minor"), "contribution", integer=True)
    cost = number(data.get("non_media_cost_per_tap_minor"), "non_media_cost", integer=True)
    cap = number(data.get("owner_cpt_cap_minor"), "owner_cap", integer=True)
    share = number(data.get("acquisition_share"), "acquisition_share", upper=1)
    missing = [field for field in ("mature", "counts_verified", "contribution_verified") if not data[field]]
    if taps == 0:
        missing.append("nonzero_taps")
    if missing:
        return {"status": "BLOCKED", "missing": missing, "cpt_ceiling_minor": None, "currency": currency}
    lower = wilson_lower(paid, taps)
    ceiling = min(cap, math.floor(max(0, lower * contribution * share - cost)))
    return {"status": "ADVISORY", "currency": currency, "cohort_id": data["cohort_id"],
            "contribution_horizon": data["contribution_horizon"], "taps": taps, "paid": paid,
            "paid_per_tap": paid / taps, "wilson_lower": lower, "cpt_ceiling_minor": ceiling,
            "source_ref": data["source_ref"], "future_profitability": "UNPROVEN"}


def content_analysis(rows, app_id, as_of):
    output = []
    seen = set()
    for row in items(rows, "content"):
        row = obj(row, "content row")
        cid = text(row.get("id"), "content id")
        if cid in seen:
            raise ValueError("duplicate content id")
        seen.add(cid)
        if row.get("app_id") != app_id:
            raise ValueError("content app scope mismatch")
        required = items(row.get("required_claims"), "required_claims")
        if not required or any(not isinstance(c, str) or not c.strip() for c in required):
            raise ValueError("required_claims must contain claim identifiers")
        if len(set(required)) != len(required):
            raise ValueError("duplicate required claim")
        factors = {k: number(row.get(k), k, upper=1) for k in
                   ("intent_fit", "observed_need", "baseline_coverage", "claim_risk")}
        effort = number(row.get("effort_days"), "effort_days")
        if effort == 0:
            raise ValueError("effort_days must be positive")
        max_age = number(row.get("max_age_days"), "max_age_days", integer=True)
        reasons, covered = [], set()
        for evidence in items(row.get("evidence"), "evidence"):
            evidence = obj(evidence, "evidence row")
            if evidence.get("app_id") != app_id:
                reasons.append("evidence_app_mismatch")
                continue
            if evidence.get("verified") is not True:
                reasons.append("unverified_evidence")
                continue
            if not public_url(evidence.get("url")):
                reasons.append("missing_public_https_source")
                continue
            if not isinstance(evidence.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", evidence["sha256"]):
                reasons.append("missing_source_hash")
                continue
            observed = timestamp(evidence.get("observed_at"), "evidence.observed_at")
            age = (as_of - observed).total_seconds() / 86400
            if age < 0 or age > max_age:
                reasons.append("stale_or_future_evidence")
                continue
            claims = items(evidence.get("claim_ids"), "evidence.claim_ids")
            if any(not isinstance(c, str) or not c.strip() for c in claims):
                raise ValueError("evidence claim identifiers must be text")
            covered.update(claims)
        if not set(required).issubset(covered):
            reasons.append("missing_required_claim_evidence")
        eligible = not reasons
        priority = (factors["intent_fit"] * factors["observed_need"] *
                    (1 - factors["baseline_coverage"]) * (1 - factors["claim_risk"]) / effort)
        if not math.isfinite(priority):
            raise ValueError("content priority overflow")
        output.append({"id": cid, "status": "ELIGIBLE" if eligible else "BLOCKED",
                       "priority": priority if eligible else None,
                       "reasons": sorted(set(reasons)), "factors": factors, "effort_days": effort})
    return sorted(output, key=lambda r: (r["status"] != "ELIGIBLE", -(r["priority"] or 0), r["id"]))


def aeo_analysis(rows, app_id, as_of):
    groups, seen = {}, set()
    for row in items(rows, "aeo"):
        row = obj(row, "aeo row")
        if row.get("app_id") != app_id:
            raise ValueError("aeo app scope mismatch")
        key = tuple(text(row.get(k), k) for k in ("engine", "locale"))
        observation_id = text(row.get("observation_id"), "observation_id")
        if observation_id in seen:
            raise ValueError("duplicate AEO observation")
        seen.add(observation_id)
        text(row.get("query_id"), "query_id")
        text(row.get("source_ref"), "source_ref")
        if timestamp(row.get("observed_at"), "aeo.observed_at") > as_of:
            raise ValueError("future AEO observation")
        if row.get("status") not in ("ok", "error"):
            raise ValueError("aeo status must be ok or error")
        group = groups.setdefault(key, {"engine": key[0], "locale": key[1], "attempted": 0,
                                       "successful": 0, "failed": 0, "mentions": 0,
                                       "citations": 0, "correct_citations": 0})
        group["attempted"] += 1
        if row["status"] == "error":
            if any(row.get(k) is not None for k in ("mention", "citation", "correct_citation", "citation_url")):
                raise ValueError("failed observation cannot contain answer outcomes")
            group["failed"] += 1
            continue
        for field in ("mention", "citation", "correct_citation"):
            if not isinstance(row.get(field), bool):
                raise ValueError(f"aeo.{field} must be boolean")
        if row["correct_citation"] and not row["citation"]:
            raise ValueError("correct citation requires a citation")
        if row["citation"] and not public_url(row.get("citation_url")):
            raise ValueError("citation requires public HTTPS URL")
        group["successful"] += 1
        for source, target in (("mention", "mentions"), ("citation", "citations"), ("correct_citation", "correct_citations")):
            group[target] += int(row[source])
    result = []
    for key in sorted(groups):
        group = groups[key]
        for count, rate in (("mentions", "mention_rate"), ("citations", "citation_rate"),
                            ("correct_citations", "correct_citation_rate")):
            group[rate] = group[count] / group["successful"] if group["successful"] else None
        group["citation_accuracy"] = group["correct_citations"] / group["citations"] if group["citations"] else None
        result.append(group)
    return result


def analyze(data):
    data = obj(data, "input")
    app_id = text(data.get("app_id"), "app_id")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", app_id):
        raise ValueError("invalid app identifier")
    as_of = timestamp(data.get("as_of"), "as_of")
    if not any(k in data for k in ("asa", "aeo", "content")):
        raise ValueError("at least one analysis section is required")
    report = {"schema": "app-growth.acquisition-analysis.v1", "app_id": app_id,
              "scope": "offline supplied-data advisory; no independent verification",
              "provider_execution": "NOT_RUN", "authorized_spend_minor_units": 0}
    if "asa" in data:
        report["asa"] = asa_analysis(data["asa"], app_id)
    if "content" in data:
        report["content"] = content_analysis(data["content"], app_id, as_of)
    if "aeo" in data:
        report["aeo"] = aeo_analysis(data["aeo"], app_id, as_of)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="UTF-8 JSON input; no files are modified")
    args = parser.parse_args(argv)
    try:
        report = analyze(json.loads(args.input.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(exc), "provider_execution": "NOT_RUN"}))
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
