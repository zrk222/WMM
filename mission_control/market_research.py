"""Bounded, source-linked market research snapshots; no provider reads or ranking claims."""
from datetime import timedelta
import hashlib
import ipaddress
from itertools import product
import math
import re
from urllib.parse import urlsplit

from .common import Invalid, digest, iso_time, required
from .pmf_contract import exact, hashed

MAX_SOURCES, MAX_PHRASES, MAX_COMPETITORS = 20, 50, 10
MAX_EXCERPT, MAX_PHRASE, MAX_BYTES = 1000, 120, 65536
METRIC_NAMES = ("search_volume", "rank", "difficulty")
MAX_INTENT_CLUSTERS = 10
EVIDENCE_ROLES = ("demand", "competitive_gap", "app_proof")
SOURCE_MAX_AGE = timedelta(days=90)


def _phrase(value):
    return " ".join(re.findall(r"[^\W_]+", required(value, "Phrase", MAX_PHRASE).casefold(), re.UNICODE))


def _normalize_excerpt(value):
    return " ".join(re.findall(r"[^\W_]+", value.casefold(), re.UNICODE))


def _url(value):
    value = required(value, "Source URL", 2048)
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        port = parsed.port
        ipaddress.ip_address(host)
    except ValueError:
        try:
            parsed = urlsplit(value)
            host = parsed.hostname or ""
            port = parsed.port
        except (ValueError, TypeError, AttributeError) as exc:
            raise Invalid("Source URL is malformed") from exc
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise Invalid("Source URL host must be a public DNS name")
    else:
        raise Invalid("Source URL host must be a public DNS name")
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password or port not in (None, 443)
            or host.casefold() in ("localhost",) or host.casefold().endswith((".local", ".internal"))):
        raise Invalid("Source URL must use public HTTPS without credentials or a custom port")
    return value


def _stamp(value, observed_at, label):
    parsed = iso_time(value)
    if parsed > iso_time(observed_at):
        raise Invalid(label + " cannot be in the future")
    return parsed


def _contains(haystack, needle):
    return bool(needle and re.search(r"(?:^|\s)" + re.escape(needle) + r"(?:$|\s)", haystack))


def _unique_rows(rows, cap, label):
    if not isinstance(rows, list) or len(rows) > cap:
        raise Invalid(label + " exceeds its bounded row count")
    return rows


def validate_snapshot(value, context, as_of):
    """Validate exact app scope, source lineage and all user-provided assertions."""
    fields = {"platform", "locale", "territory", "observed_at", "own_listing", "sources", "phrases", "competitors"}
    if isinstance(value, dict) and "intent_clusters" in value:
        fields.add("intent_clusters")
    exact(value, fields)
    if value["platform"] not in ("iOS", "Android"):
        raise Invalid("Platform must be iOS or Android")
    if value["locale"] != context.get("locale") or not context.get("locale"):
        raise Invalid("Market research locale must match the configured app locale")
    if not isinstance(value["territory"], str) or not re.fullmatch(r"[A-Z]{2}", value["territory"]):
        raise Invalid("Territory must be a two-letter uppercase country code")
    observed = _stamp(value["observed_at"], as_of, "Observation date")
    try:
        import json
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise Invalid("Snapshot must contain finite JSON values") from exc
    if len(encoded) > MAX_BYTES:
        raise Invalid("Market research snapshot exceeds 64 KiB")

    sources = _unique_rows(value["sources"], MAX_SOURCES, "Sources")
    source_ids = set()
    normalized_sources = []
    for src in sources:
        exact(src, {"id", "url", "sha256", "retrieved_at", "coverage", "excerpt"})
        sid = required(src["id"], "Source ID", 80)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}", sid) or sid in source_ids:
            raise Invalid("Source IDs must be unique bounded identifiers")
        source_ids.add(sid)
        url = _url(src["url"])
        hashed(src["sha256"])
        retrieved = _stamp(src["retrieved_at"], observed.isoformat(), "Source retrieval date")
        coverage = src["coverage"]
        if coverage not in ("COMPLETE", "PARTIAL", "NO_RESULTS"):
            raise Invalid("Source coverage must be COMPLETE, PARTIAL, or NO_RESULTS")
        excerpt = src["excerpt"]
        if not isinstance(excerpt, str) or len(excerpt) > MAX_EXCERPT:
            raise Invalid("Source excerpt exceeds 1000 characters")
        if excerpt and hashlib.sha256(excerpt.encode()).hexdigest() != src["sha256"]:
            raise Invalid("Source excerpt does not match its SHA-256")
        normalized_sources.append(dict(src, id=sid, url=url, retrieved_at=retrieved.isoformat()))

    phrases = _unique_rows(value["phrases"], MAX_PHRASES, "Phrases")
    phrase_ids, canonical_phrases = set(), set()
    normalized_phrases = []
    for row in phrases:
        exact(row, {"id", "phrase", "source_ids", "observed", "inferred", "metrics"})
        pid = required(row["id"], "Phrase ID", 80)
        phrase = required(row["phrase"], "Phrase", MAX_PHRASE)
        canonical = _phrase(phrase)
        if not canonical or pid in phrase_ids or canonical in canonical_phrases:
            raise Invalid("Phrase IDs and normalized phrases must be unique and nonempty")
        phrase_ids.add(pid)
        canonical_phrases.add(canonical)
        refs = row["source_ids"]
        if not isinstance(refs, list) or len(refs) > MAX_SOURCES or len(refs) != len(set(refs)) or any(ref not in source_ids for ref in refs):
            raise Invalid("Phrase source IDs must refer to unique sources in this snapshot")
        exact(row["observed"], {"demand_signal", "competitor_position"})
        for key in ("demand_signal", "competitor_position"):
            observed_value = row["observed"][key]
            if observed_value is not None and (not isinstance(observed_value, str) or len(observed_value) > 500):
                raise Invalid("Observed phrase fields must be short operator-supplied text or null")
        exact(row["inferred"], {"intent", "relevance"})
        intent = row["inferred"]["intent"]
        if intent is not None and (not isinstance(intent, str) or len(intent) > 500):
            raise Invalid("Analyst intent must be text or null")
        relevance = row["inferred"]["relevance"]
        if relevance is not None and (isinstance(relevance, bool) or not isinstance(relevance, (float, int)) or not math.isfinite(relevance) or not 0 <= relevance <= 1):
            raise Invalid("Analyst relevance must be a finite fraction from 0 to 1")
        metrics = row["metrics"]
        exact(metrics, set(METRIC_NAMES))
        clean_metrics = {}
        for name in METRIC_NAMES:
            metric = metrics[name]
            if metric is None:
                clean_metrics[name] = None
                continue
            exact(metric, {"value", "source_id"})
            number = metric["value"]
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
                raise Invalid("Sourced metrics must be finite nonnegative numbers")
            if metric["source_id"] not in refs:
                raise Invalid("Every supplied metric must cite this phrase's source ID")
            clean_metrics[name] = dict(value=number, source_id=metric["source_id"], provenance="OPERATOR_ASSERTION", provider_verified=False)
        normalized_phrases.append(dict(id=pid, phrase=phrase, normalized_phrase=canonical, source_ids=refs,
            observed=dict(row["observed"], provenance="OPERATOR_SUPPLIED"),
            inferred=dict(row["inferred"], provenance="ANALYST_INFERRED"), metrics=clean_metrics))

    competitors = _unique_rows(value["competitors"], MAX_COMPETITORS, "Competitors")
    competitor_ids, comp_normalized = set(), []
    for comp in competitors:
        exact(comp, {"id", "name", "listing_excerpt", "source_id"})
        cid = required(comp["id"], "Competitor ID", 80)
        if cid in competitor_ids or comp["source_id"] not in source_ids:
            raise Invalid("Competitor IDs must be unique and source must belong to the snapshot")
        competitor_ids.add(cid)
        excerpt = comp["listing_excerpt"]
        if not isinstance(excerpt, str) or len(excerpt) > MAX_EXCERPT:
            raise Invalid("Competitor listing excerpt exceeds 1000 characters")
        if excerpt and comp["source_id"] not in source_ids:
            raise Invalid("Competitor listing excerpt requires a source")
        comp_normalized.append(dict(id=cid, name=required(comp["name"], "Competitor name", 120),
                                    listing_excerpt=excerpt, source_id=comp["source_id"]))

    own = value["own_listing"]
    exact(own, {"excerpt", "source_id"})
    if not isinstance(own["excerpt"], str) or len(own["excerpt"]) > MAX_EXCERPT or own["source_id"] not in source_ids:
        raise Invalid("Own listing excerpt must be bounded and cite a snapshot source")
    if "intent_clusters" in value:
        value = dict(value, intent_clusters=_validate_intent_clusters(value["intent_clusters"], normalized_phrases, source_ids))
    return dict(value, observed_at=observed.isoformat(), sources=normalized_sources, phrases=normalized_phrases,
                competitors=[dict(row, provenance="OPERATOR_SUPPLIED") for row in comp_normalized],
                own_listing=dict(own, provenance="OPERATOR_SUPPLIED"))


def _cluster_refs(value, allowed, label):
    if (not isinstance(value, list) or len(value) > len(allowed)
            or any(not isinstance(ref, str) or ref not in allowed for ref in value)
            or len(set(value)) != len(value)):
        raise Invalid(label + " must contain unique references from this snapshot")
    return value


def _validate_intent_clusters(rows, phrases, source_ids):
    phrase_sources = {row["id"]: set(row["source_ids"]) for row in phrases}
    result, ids, intents, assigned = [], set(), set(), set()
    for row in _unique_rows(rows, MAX_INTENT_CLUSTERS, "Intent clusters"):
        exact(row, {"id", "intent", "phrase_ids", "evidence", "test"})
        cid = required(row["id"], "Cluster ID", 80)
        intent = required(row["intent"], "Buyer intent", 160)
        key = _normalize_excerpt(intent)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}", cid) or cid in ids:
            raise Invalid("Intent cluster IDs must be unique bounded identifiers")
        if not key or key in intents:
            raise Invalid("Buyer intents must be distinct")
        refs = _cluster_refs(row["phrase_ids"], phrase_sources, "Cluster phrases")
        if not refs or assigned.intersection(refs):
            raise Invalid("Each cluster needs phrases; a phrase may belong to only one cluster")
        exact(row["evidence"], EVIDENCE_ROLES)
        evidence = {role: _cluster_refs(row["evidence"][role], source_ids, role) for role in EVIDENCE_ROLES}
        if set(evidence["demand"]).difference(set().union(*(phrase_sources[ref] for ref in refs))):
            raise Invalid("Demand evidence must be linked to a phrase in this cluster")
        test = row["test"]
        if test is not None:
            exact(test, {"change", "hypothesis"})
            test = dict(change=required(test["change"], "One proposed change", 500),
                        hypothesis=required(test["hypothesis"], "Test hypothesis", 500))
        result.append(dict(id=cid, intent=intent, phrase_ids=refs, evidence=evidence, test=test))
        ids.add(cid)
        intents.add(key)
        assigned.update(refs)
    return result


def _intent_opportunities(snapshot, as_of):
    sources = {row["id"]: row for row in snapshot["sources"]}
    cutoff = iso_time(as_of) - SOURCE_MAX_AGE
    eligible = {sid: src["sha256"] for sid, src in sources.items()
                if src["coverage"] == "COMPLETE" and src["excerpt"].strip()
                and iso_time(src["retrieved_at"]) >= cutoff}
    phrases = {row["id"]: row["phrase"] for row in snapshot["phrases"]}
    opportunities = []
    for cluster in snapshot.get("intent_clusters", []):
        support = {role: sorted({eligible[sid] for sid in refs if sid in eligible})
                   for role, refs in cluster["evidence"].items()}
        missing = [role for role in EVIDENCE_ROLES if not support[role]]
        if not missing and not any(len(set(group)) == len(EVIDENCE_ROLES)
                                   for group in product(*(support[role] for role in EVIDENCE_ROLES))):
            missing.append("distinct_evidence")
        if snapshot["own_listing"]["source_id"] not in eligible or not snapshot["own_listing"]["excerpt"].strip():
            missing.append("current_listing")
        if cluster["test"] is None:
            missing.append("test_hypothesis")
        opportunities.append(dict(cluster, phrases=[phrases[ref] for ref in cluster["phrase_ids"]],
            status="COLLECT_EVIDENCE" if missing else "REVIEW_TEST", missing=missing,
            next_action="Fill the evidence gaps before choosing a test." if missing else
            "Review the sources and freeze a control, metric, sample and stopping rule before launching.",
            evidence_status="OPERATOR_SUPPLIED", organic_demand_verified=False))
    return sorted(opportunities, key=lambda row: (len(row["missing"]), row["id"]))


def analyze_snapshot(snapshot, as_of):
    """Derive reproducible advisory coverage and copy-test candidates only."""
    sources = snapshot["sources"]
    stale = any(iso_time(as_of) - iso_time(src["retrieved_at"]) > SOURCE_MAX_AGE for src in sources)
    coverage_states = {s["coverage"] for s in sources}
    if not snapshot["phrases"] or coverage_states == {"NO_RESULTS"}:
        state, action = "NO_RESULTS", "Capture a broader query"
    elif stale:
        state, action = "STALE", "Capture current source evidence for this app locale"
    elif "PARTIAL" in coverage_states or "NO_RESULTS" in coverage_states:
        state, action = "PARTIAL", "Complete the source capture before comparing candidates"
    else:
        state, action = "OBSERVED", "Review the sourced candidates with a localized reviewer"

    own = _normalize_excerpt(snapshot["own_listing"]["excerpt"])
    competitor_text = [(c["id"], _normalize_excerpt(c["listing_excerpt"])) for c in snapshot["competitors"]]
    candidates = []
    phrase_results = []
    observed_phrase_count = 0
    for row in snapshot["phrases"]:
        sourced = bool(row["source_ids"])
        observed_phrase_count += int(sourced)
        overlap = _contains(own, row["normalized_phrase"])
        overlaps = [cid for cid, text in competitor_text if _contains(text, row["normalized_phrase"])]
        phrase_results.append(dict(id=row["id"], phrase=row["phrase"], normalized_phrase=row["normalized_phrase"],
            source_ids=row["source_ids"], observed=row["observed"], inferred=row["inferred"], metrics=row["metrics"],
            own_listing_overlap=overlap, competitor_ids=overlaps))
        if sourced and (overlap or overlaps or row["inferred"]["relevance"] is not None):
            why = "Phrase occurs in supplied own listing" if overlap else ("Phrase occurs in supplied competitor listing" if overlaps else "Analyst supplied relevance hypothesis")
            candidates.append(dict(phrase=row["phrase"], reason=why, own_listing_overlap=overlap,
                competitor_ids=overlaps, suggested_test="Review a localized listing copy test", metrics=row["metrics"]))
    candidates.sort(key=lambda item: (not bool(item["competitor_ids"]), not item["own_listing_overlap"], item["phrase"].casefold()))
    return dict(state=state, status=state, next_action=action,
        coverage=dict(phrases=len(snapshot["phrases"]), sourced_phrases=observed_phrase_count,
            fraction=(observed_phrase_count / len(snapshot["phrases"]) if snapshot["phrases"] else None),
            source_count=len(sources),
            source_states={key: sum(s["coverage"] == key for s in sources) for key in ("COMPLETE", "PARTIAL", "NO_RESULTS")},
            normalized_unique_phrases=len({p["normalized_phrase"] for p in snapshot["phrases"]})),
        candidates=candidates[:25], intent_opportunities=_intent_opportunities(snapshot, as_of), provider_verified=False, outcomes_verified=False, external_writes=False,
        phrase_results=phrase_results, own_listing=snapshot["own_listing"], competitors=snapshot["competitors"],
        source_provenance="OPERATOR_SUPPLIED_SOURCE_SNAPSHOT",
        organic_rank_inferred=False, paid_counts_used=False,
        scope="Supplied source snapshots and analyst hypotheses only; no organic demand, ranking, growth, paid performance or causal outcome is inferred.",
        source_hash=digest(snapshot))


def market_research_readout(data, as_of):
    """Mark aged source snapshots stale while preserving their content and assertions."""
    snapshot = validate_snapshot(data["snapshot"], {"locale": data["snapshot"]["locale"]}, as_of)
    return analyze_snapshot(snapshot, as_of)


def agent_contract():
    """Return exact caller schema and a compact valid-shaped fixture template."""
    return {
        "kind": "MARKET_RESEARCH",
        "entry_fields": {"release": "current configured release", "snapshot": {
            "platform": "iOS|Android", "locale": "must equal app locale", "territory": "US",
            "observed_at": "timezone-bearing ISO timestamp", "own_listing": {"excerpt": "supplied listing text", "source_id": "src-1"},
            "sources": [{"id": "src-1", "url": "https://example.com/report", "sha256": "64 lowercase hex chars",
                "retrieved_at": "timezone-bearing ISO timestamp", "coverage": "COMPLETE|PARTIAL|NO_RESULTS", "excerpt": "captured evidence, max 1000 chars"}],
            "phrases": [{"id": "phrase-1", "phrase": "bounded search phrase", "source_ids": ["src-1"],
                "observed": {"demand_signal": None, "competitor_position": None},
                "inferred": {"intent": None, "relevance": None},
                "metrics": {name: None for name in METRIC_NAMES}}],
            "competitors": [{"id": "competitor-1", "name": "Competitor", "listing_excerpt": "supplied listing text", "source_id": "src-1"}],
        }},
        "bounds": {"sources": MAX_SOURCES, "phrases": MAX_PHRASES, "competitors": MAX_COMPETITORS,
            "phrase_chars": MAX_PHRASE, "excerpt_chars": MAX_EXCERPT, "snapshot_bytes": MAX_BYTES, "candidates": 25, "intent_clusters": MAX_INTENT_CLUSTERS},
        "provenance": {"observed": "operator-supplied text and source snapshots", "inferred": "analyst intent/relevance hypothesis",
            "metrics": "each non-null metric requires value and source_id; provenance=OPERATOR_ASSERTION; provider_verified=false"},
        "optional_snapshot_fields": {"intent_clusters": [{
            "id": "cluster-1", "intent": "one buyer problem", "phrase_ids": ["phrase-1"],
            "evidence": {"demand": [], "competitive_gap": [], "app_proof": []},
            "test": {"change": "one listing or creative change", "hypothesis": "expected effect and why"},
        }]},
        "intent_cluster_guidance": "Supply fresh, distinct evidence for each role. Separate actual search observations from language hypotheses. An empty role stays unknown. REVIEW_TEST is advisory and does not grant approval.",
        "no_network": True,
    }
