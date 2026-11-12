"""Bounded external research envelopes; observations are not independently verified."""

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlsplit

from .common import Invalid, digest, iso_time, required
from .viral_policy import FIELDS, PLATFORMS, observation, qualify

HOSTS = {
    "tiktok": {"tiktok.com", "www.tiktok.com"},
    "facebook": {"facebook.com", "www.facebook.com"},
    "instagram": {"instagram.com", "www.instagram.com"},
    "youtube": {"youtube.com", "www.youtube.com"},
}
# YouTube already binds the exact Shorts link and ID in observation().
POST_PATHS = {
    "facebook": re.compile(r"/(?:[A-Za-z0-9._-]+/)?(?:reels?|videos|posts)/(?P<post>[A-Za-z0-9_-]+)/?"),
    "instagram": re.compile(r"/(?:[A-Za-z0-9._-]+/)?(?:reel|p|tv)/(?P<post>[A-Za-z0-9_-]+)/?"),
    "tiktok": re.compile(r"/@[A-Za-z0-9._-]+/video/(?P<post>[A-Za-z0-9_-]+)/?"),
}
HEX = re.compile(r"[0-9a-f]{64}\Z")
FAILURE_CODES = ("LOGIN", "CAPTCHA", "TIMEOUT", "UNAVAILABLE", "EMPTY", "PARTIAL")


def collector_contract():
    """Give CLI and MCP collectors the exact claim and submission shapes."""
    return {
        "claim": {"operation": "organic-video.claim", "fields": ["task_id", "task_hash"]},
        "submit": {
            "operation": "organic-video.submit",
            "fields": ["task_id", "result"],
            "result_fields": [
                "task_id",
                "task_hash",
                "claim_id",
                "collected_at",
                "read_count",
                "candidates",
                "failures",
                "execution",
            ],
            "execution": "LIVE_EXTERNAL_AGENT",
        },
        "candidate_fields": ["candidate", "history", "evidence", "relevance", "kind", "rights"],
        "observation_fields": sorted(FIELDS),
        "evidence_fields": ["post_id", "url", "observed_at", "observation_hash", "source_sha256"],
        "failure_fields": ["source", "code"],
        "failure_codes": list(FAILURE_CODES),
        "direct_post_examples": {
            "facebook": "https://www.facebook.com/reel/12345678901",
            "instagram": "https://www.instagram.com/reel/ABCdef12345/",
            "tiktok": "https://www.tiktok.com/@example/video/12345678901",
            "youtube": "https://www.youtube.com/shorts/ABCdef12345",
        },
        "post_identity": "Use the exact post ID or shortcode in the direct link, without share parameters.",
        "coverage": "Use permitted metadata reads for each selected channel. Report unavailable or empty sources explicitly.",
        "handoff": "Owner review can adopt qualified references from partial searches. Rights and footage stay separate.",
    }


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise Invalid("Use the exact discovery fields")


def bounded(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Invalid("Discovery budget is outside its supported bound")
    return value


def _text(value, label, limit=200):
    return required(value, label, limit)


def _url(value, hosts):
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in hosts
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
            and not parsed.fragment
            and not parsed.query
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise Invalid("Observation must use an allowed HTTPS platform host")
    return parsed.path


def discovery_task(app, policy, query) -> object:
    """Freeze owner-selected bounds; readiness does not imply a live collection."""
    exact(app, ("id", "version", "hash"))
    exact(
        policy,
        ("recipient_grant_id", "platforms", "hosts", "expires", "max_candidates", "max_reads", "max_seconds", "access"),
    )
    exact(query, ("genre", "app_type", "search_terms"))
    _text(app["id"], "App ID", 120)
    bounded(app["version"], 1, 1000000000)
    if not isinstance(app["hash"], str) or not HEX.fullmatch(app["hash"]):
        raise Invalid("Use the current app hash")
    _text(policy["recipient_grant_id"], "Recipient grant", 120)
    platforms = policy["platforms"]
    if (
        not isinstance(platforms, list)
        or not platforms
        or len(platforms) > len(PLATFORMS)
        or any(not isinstance(p, str) or p not in PLATFORMS for p in platforms)
        or len(set(platforms)) != len(platforms)
    ):
        raise Invalid("Choose unique supported discovery platforms")
    hosts = policy["hosts"]
    allowed = set().union(*(HOSTS[p] for p in platforms))
    if (
        not isinstance(hosts, list)
        or not hosts
        or any(not isinstance(h, str) for h in hosts)
        or len(hosts) != len(set(hosts))
        or not set(hosts) <= allowed
    ):
        raise Invalid("Choose exact supported discovery hosts")
    if policy["access"] not in ("PUBLIC_WEB", "OWNER_AUTHORIZED_PLATFORM", "PERMITTED_API"):
        raise Invalid("Choose the separately authorized collector capability")
    bounded(policy["max_candidates"], 1, 20)
    bounded(policy["max_reads"], 1, 500)
    bounded(policy["max_seconds"], 1, 3600)
    expires = iso_time(policy["expires"])
    now = datetime.now(timezone.utc)
    if not now < expires <= now + timedelta(hours=24):
        raise Invalid("Discovery authority must expire within 24 hours")
    for key in ("genre", "app_type", "search_terms"):
        _text(query[key], key, 500 if key == "search_terms" else 120)
    return {
        "schema": "growth.organic-video-discovery-task.v1",
        "app": dict(app),
        "policy": dict(policy, platforms=sorted(platforms), hosts=sorted(hosts), expires=expires.isoformat()),
        "query": dict(query),
        "collection": "NOT_RUN",
        "authority": "EXTERNAL_PERSONAL_AGENT_ONLY",
        "boundaries": {
            "content": "PUBLIC_POST_METADATA_ONLY",
            "private_messages": "FORBIDDEN",
            "social_writes": "FORBIDDEN",
            "media_download": "FORBIDDEN",
            "wmm_credentials": "NOT_DELEGATED",
            "tool_enforcement": "EXTERNAL_AGENT",
        },
    }


def validate_submission(task, result, *, require_post_links=True) -> object:
    """Validate exact observation identities, bounded provenance and chronology."""
    exact(
        result,
        ("task_id", "task_hash", "claim_id", "collected_at", "read_count", "candidates", "failures", "execution"),
    )
    if result["task_hash"] != digest(task):
        raise Invalid("Discovery task hash changed")
    _text(result["task_id"], "Task ID", 120)
    _text(result["claim_id"], "Claim ID", 120)
    if result["execution"] != "LIVE_EXTERNAL_AGENT":
        raise Invalid("Saved-pool results are not live collection")
    stamp = iso_time(result["collected_at"])
    now = datetime.now(timezone.utc)
    if stamp > now or stamp < now - timedelta(hours=24) or stamp > iso_time(task["policy"]["expires"]):
        raise Invalid("Collection observation is outside the current task window")
    bounded(result["read_count"], 1, task["policy"]["max_reads"])
    candidates, failures = result["candidates"], result["failures"]
    if not isinstance(candidates, list) or len(candidates) > task["policy"]["max_candidates"]:
        raise Invalid("Candidate count exceeds the task budget")
    if not isinstance(failures, list) or len(failures) > task["policy"]["max_reads"]:
        raise Invalid("Source failures exceed the task budget")
    if not candidates and not failures:
        raise Invalid("Collection must retain observations or named failures")
    for failure in failures:
        exact(failure, ("source", "code"))
        _url(failure["source"], task["policy"]["hosts"])
        if failure["code"] not in FAILURE_CODES:
            raise Invalid("Use a supported discovery failure")
    seen = set()
    for item in candidates:
        exact(item, ("candidate", "history", "evidence", "relevance", "kind", "rights"))
        if item["relevance"] not in ("MATCH", "UNKNOWN", "MISMATCH"):
            raise Invalid("Use a supported relevance status")
        if item["kind"] not in ("REFERENCE", "UGC") or item["rights"] not in ("UNKNOWN", "ALLOWED", "DENIED"):
            raise Invalid("Use supported source and rights classifications")
        history = item["history"]
        if not isinstance(history, list) or len(history) > 20:
            raise Invalid("At most 20 baseline observations may be submitted")
        observations = [item["candidate"], *history]
        normalized = []
        for index, row in enumerate(observations):
            # UGC is exempt from a performance requirement, including supplying views.
            if (
                index == 0
                and item["kind"] == "UGC"
                and isinstance(row, dict)
                and "views" in row
                and row["views"] is None
            ):
                normalized_row = observation({**row, "views": 0}, stamp)
                normalized_row["views"] = None
            else:
                normalized_row = observation(row, stamp)
            normalized.append(normalized_row)
        for row in normalized:
            if row["platform"] not in task["policy"]["platforms"]:
                raise Invalid("Observation platform is outside task scope")
            platform = row["platform"]
            path = _url(row["url"], set(task["policy"]["hosts"]) & HOSTS[platform])
            post_path = POST_PATHS.get(platform)
            if require_post_links and post_path:
                match = post_path.fullmatch(path)
                if match is None:
                    raise Invalid(f"Use a direct {platform} post link for the candidate and each baseline observation")
                if match["post"] != row["post_id"]:
                    raise Invalid(f"{platform.capitalize()} post identity must match the direct link")
            if iso_time(row["observed_at"]) < stamp - timedelta(hours=24):
                raise Invalid("Observation is stale")
        key = (normalized[0]["platform"], normalized[0]["post_id"])
        if key in seen:
            raise Invalid("Duplicate candidate identity")
        seen.add(key)
        evidence = item["evidence"]
        if not isinstance(evidence, list) or len(evidence) != len(normalized):
            raise Invalid("Every observation needs its own source receipt")
        for row, receipt in zip(normalized, evidence):
            exact(receipt, ("post_id", "url", "observed_at", "observation_hash", "source_sha256"))
            if (
                receipt["post_id"] != row["post_id"]
                or receipt["url"] != row["url"]
                or iso_time(receipt["observed_at"]) != iso_time(row["observed_at"])
                or receipt["observation_hash"] != digest(row)
                or not isinstance(receipt["source_sha256"], str)
                or not HEX.fullmatch(receipt["source_sha256"])
            ):
                raise Invalid("Observation and source receipt differ")
    return result


def collection_coverage(task, submission):
    """Summarize retained candidate and failure counts for every selected platform."""
    coverage = {platform: {"candidates": 0, "failures": 0} for platform in task["policy"]["platforms"]}
    if submission:
        for item in submission["candidates"]:
            coverage[item["candidate"]["platform"]]["candidates"] += 1
        for failure in submission["failures"]:
            host = urlsplit(failure["source"]).hostname
            for platform in coverage:
                if host in HOSTS[platform]:
                    coverage[platform]["failures"] += 1
                    break
    return coverage


def qualify_submission(task, result, *, require_post_links=True) -> object:
    """Preserve existing qualification and separate its claims from source rights."""
    validate_submission(task, result, require_post_links=require_post_links)
    output = []
    for item in result["candidates"]:
        if item["kind"] == "UGC":
            receipt = {
                "qualification": "UGC_EXEMPT",
                "collection_verification": "REQUIRED",
                "human_review": "REQUIRED",
                "reuse_permission": "NOT_ESTABLISHED",
            }
            status = "UGC_OWNER_REVIEW_REQUIRED"
        else:
            receipt = qualify(item["candidate"], item["history"], result["collected_at"])
            outcome = receipt["qualification"]
            if item["relevance"] != "MATCH":
                status = "RELEVANCE_REVIEW_REQUIRED"
            elif outcome == "QUALIFIED_BY_REPORTED_COUNTS":
                status = "COLLECTION_REVIEW_REQUIRED"
            else:
                status = outcome
        output.append(
            {
                "candidate_id": item["candidate"]["post_id"],
                "status": status,
                "qualification": receipt,
                "collector_asserted_rights": item["rights"],
                "reuse_permission": "NOT_ESTABLISHED",
                "publication": "NOT_RUN",
            }
        )
    return {
        "schema": "growth.organic-video-discovery-result.v1",
        "items": output,
        "source_failures": result["failures"],
        "collection_verification": "REQUIRED",
        "publication": "NOT_RUN",
    }
