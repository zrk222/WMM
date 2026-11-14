"""Stable marketing vocabulary shared by discovery and agent manifests."""

from copy import deepcopy

from .common import digest

ALIASES = {
    "narratives": {"app demo": "APP_DEMO"},
    "treatments": {"talking head": "TALKING_HEAD", "screen capture": "SCREEN_RECORDING"},
}


def filter_term(axis: str, value: str) -> str:
    """Resolve only an explicit alias in the requested query axis."""
    return ALIASES.get(axis, {}).get(" ".join(value.casefold().split()), value)


INDUSTRIES = {
    "BUSINESS",
    "EDUCATION",
    "FINANCE",
    "HEALTH_FITNESS",
    "GAMING",
    "LIFESTYLE",
    "ENTERTAINMENT",
    "ECOMMERCE",
    "OTHER",
    "UNKNOWN",
}
NARRATIVES = {
    "APP_DEMO",
    "TUTORIAL",
    "PROBLEM_SOLUTION",
    "TESTIMONIAL",
    "STORY",
    "BEFORE_AFTER",
    "MEME_TREND",
    "LISTICLE",
    "EDUCATIONAL",
    "ENTERTAINMENT",
    "OTHER",
    "UNKNOWN",
}
TREATMENTS = {
    "TALKING_HEAD",
    "SCREEN_RECORDING",
    "SLIDESHOW",
    "ANIMATION",
    "TEXT_HEAVY",
    "LIVE_ACTION",
    "MIXED",
    "OTHER",
    "UNKNOWN",
}


def ontology() -> dict[str, object]:
    """Return a fresh vocabulary with stable identifiers and explicit evidence boundaries."""
    body = {
        "schema": "growth.marketing-ontology.v1",
        "axes": {
            "industry": sorted(INDUSTRIES),
            "narrative": sorted(NARRATIVES),
            "treatment": sorted(TREATMENTS),
        },
        "entities": {
            "SOURCE": "An observed or supplied reference with provenance.",
            "CANDIDATE": "A relevant observed source awaiting one or more checks.",
            "QUALIFIED_REFERENCE": "A reference that passed applicable discovery checks.",
            "RIGHTS_DECISION": "A separate, current, source-specific owner decision.",
            "DRAFT_ARTIFACT": "A generated or edited asset before publication.",
            "DELIVERY_RECEIPT": "Observed provider delivery of an exact artifact or message.",
            "MEASUREMENT": "An observed metric with a source, time window and denominator where applicable.",
        },
        "search_rules": {
            "aliases": deepcopy(ALIASES),
            "routing": {
                "viral video": "Use organic-video.claim only with an existing owner-prepared task.",
                "app store keywords": "Use workspace.read to establish current app scope before keyword research.",
                "qualified references": "Use discovery.history to find retained research; check qualification separately.",
            },
            "fallback": "Keep the original term and use UNKNOWN for an unclassified axis.",
        },
        "relationships": [
            ["CANDIDATE", "observed_from", "SOURCE"],
            ["QUALIFIED_REFERENCE", "qualified_from", "CANDIDATE"],
            ["RIGHTS_DECISION", "applies_to", "SOURCE"],
            ["DRAFT_ARTIFACT", "may_reference", "QUALIFIED_REFERENCE"],
            ["DELIVERY_RECEIPT", "verifies_delivery_of", "DRAFT_ARTIFACT"],
            ["MEASUREMENT", "may_attribute_to", "DELIVERY_RECEIPT"],
        ],
        "toolchain_guidance": {
            "authority": "ADVISORY_ONLY",
            "discover": "Check the current operation catalog before promising any tool or provider. If unavailable, report the reason and preserve draft progress.",
            "hypit": "Keep the selected acquisition workflow. Compare creative variants with the same audience, offer, real app proof, destination and declared metric.",
            "rea_video": "Use permitted local footage to extract time-aligned observations. Separate detected cuts from interpretations; use the original frame or timestamp as evidence.",
            "genjutsu": "Use only for a testable variant when the owner selects metered generation and approves the exact cost and media disclosure. Reconcile an uncertain provider request before retrying.",
            "evaluation": "Change one meaningful creative variable. Check hook clarity, caption legibility, authentic app proof and the call to action before proposing publication.",
            "learning": "Log failed tests as well as wins. Show sample sizes, missing tracking and attribution limits. Recommend Continue, Revise, Stop or Collect more data without inventing lift.",
        },
        "evidence_status": {
            "QUALIFIED_BY_REPORTED_COUNTS": "COLLECTION_REVIEW_REQUIRED",
            "UGC_EXEMPT": "UGC_OWNER_REVIEW_REQUIRED",
            "INSUFFICIENT_BASELINE": "CANDIDATE_ONLY",
            "NOT_REPORTED": "UNKNOWN_COVERAGE",
        },
        "rules": [
            "Keep original labels separate from classified industry, narrative and treatment.",
            "Qualification does not establish rights; a draft does not establish delivery.",
            "Views, impressions, installs and registrations are distinct metrics.",
            "Delivery does not establish attribution or causal lift.",
            "Record missing data as unknown, never as zero unless observed.",
        ],
    }
    return dict(body, ontology_sha256=digest(body))
