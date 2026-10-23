"""Source-linked listing preflight; no ranking, policy approval or publication claims."""
import re
from collections import Counter
from datetime import timedelta
from .common import Invalid, digest, iso_time, safe_data

RULE_VERSION = "2026-10-22.v1"
REVIEWED_AT = "2026-10-22T00:00:00+00:00"
LIMITS = {"iOS": {"title": 30, "subtitle": 30, "keywords": 100, "description": 4000, "promotional_text": 170},
          "Android": {"title": 30, "short_description": 80, "description": 4000}}
SOURCES = {"iOS": ["https://developer.apple.com/app-store/product-page/", "https://developer.apple.com/app-store/product-page-optimization/", "https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information"],
           "Android": ["https://support.google.com/googleplay/android-developer/answer/13393723", "https://support.google.com/googleplay/android-developer/answer/12053285"]}
SURFACES = {"iOS": {"MANUAL_METADATA": set(LIMITS["iOS"]), "PRODUCT_PAGE_OPTIMIZATION": {"icon", "screenshots", "app_preview"}},
            "Android": {"MANUAL_METADATA": set(LIMITS["Android"]), "LOCALIZED_LISTING_EXPERIMENT": {"short_description", "description", "icon", "feature_graphic", "screenshots"},
                        "DEFAULT_GRAPHICS_EXPERIMENT": {"icon", "feature_graphic", "screenshots"}}}


def issue(field, code, correction):
    """Keep concrete repair guidance separate from original supplied text."""
    return {"field": field, "code": code, "correction": correction}


def rule_findings(version, observed_at):
    """Expire the reviewed rule snapshot after its explicit review horizon."""
    stamp = iso_time(observed_at)
    fresh = iso_time(REVIEWED_AT) <= stamp <= iso_time(REVIEWED_AT) + timedelta(days=90)
    if version != RULE_VERSION or not fresh:
        return [issue("rule_version", "RULE_REVIEW_NEEDED", "Recheck official rules and select the reviewed rule version before relying on this preflight.")]
    return []

def validate_listing(value, observed_at) -> dict:
    """Evaluate one versioned localized listing without modifying its source."""
    safe_data(value)
    fields = {"platform", "locale", "fields", "surface", "test_fields", "rule_version"}
    if not isinstance(value, dict) or set(value) != fields:
        raise Invalid("Listing preflight needs platform, locale, fields, surface, test fields and rule version")
    platform = value["platform"]
    if not isinstance(platform, str) or platform not in LIMITS:
        raise Invalid("Choose iOS or Android")
    if not isinstance(value["locale"], str) or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value["locale"]):
        raise Invalid("Use an explicit language or language-region locale")
    observations, findings = field_findings(platform, value["fields"])
    findings += keyword_findings(value["fields"]) if platform == "iOS" else []
    findings += surface_findings(platform, value["surface"], value["test_fields"])
    findings += rule_findings(value["rule_version"], observed_at)
    return {"platform": platform, "locale": value["locale"], "rule_version": RULE_VERSION,
            "rules_reviewed_at": REVIEWED_AT, "sources": SOURCES[platform], "fields": observations,
            "findings": findings, "source_hash": digest(value), "original": value,
            "status": "NEEDS_REPAIR" if findings else "READY_FOR_REVIEW", "external_writes": False,
            "claims_verified": False, "provider_approved": False,
            "review_required": ["Verify every claim against current product evidence and rights", "Review localized meaning with a native-language reviewer", "Confirm provider character counters and current rules"],
            "scope": "Deterministic preflight only. Counts use Unicode code points; provider counters remain authoritative. No ranking prediction, experiment execution or publication."}

def field_findings(platform, fields) -> tuple:
    """Report missing, extra and overlength fields with explicit character counts."""
    if not isinstance(fields, dict) or set(fields) - set(LIMITS[platform]):
        raise Invalid("Listing fields do not match the chosen store")
    observations, findings = [], []
    optional = {"promotional_text"} if platform == "iOS" else set()
    for name, maximum in LIMITS[platform].items():
        text = fields.get(name, "")
        if not isinstance(text, str):
            raise Invalid("Listing fields must contain text")
        observations.append({"field": name, "characters": len(text), "maximum_characters": maximum, "text": text})
        if name not in optional and not text.strip():
            findings.append(issue(name, "MISSING", "Supply truthful localized " + name + "."))
        if len(text) > maximum:
            findings.append(issue(name, "TOO_LONG", "Shorten this field to " + str(maximum) + " characters; review meaning before replacing it."))
        if re.search(r"(?i)(?:#1\b|\bguaranteed\b|\b100%\s+(?:safe|effective)\b|\bbest\s+app\b)", text):
            findings.append(issue(name, "CLAIM_REVIEW", "Remove unsupported ranking or absolute outcome claims, or attach independently reviewed substantiation."))
    return observations, findings

def keyword_findings(fields) -> list:
    """Flag duplicate keyword tokens without imposing an invented density target."""
    text = fields.get("keywords", "")
    words = re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
    repeated = sorted(word for word, count in Counter(words).items() if count > 1)
    findings = []
    if len(text.encode("utf-8")) > 100:
        findings.append(issue("keywords", "KEYWORD_BYTE_REVIEW", "App Store Connect reference also specifies 100 bytes. Reduce the UTF-8 keyword payload or verify the current provider counter for this locale."))
    if repeated:
        findings.append(issue("keywords", "DUPLICATE_KEYWORD", "Review repeated words: " + ", ".join(repeated) + "; preserve intent while removing duplication."))
    if ", " in text or " ," in text:
        findings.append(issue("keywords", "SEPARATOR_SPACING", "Remove spaces around commas; spaces inside keyword phrases are permitted."))
    return findings

def surface_findings(platform, surface, test_fields) -> list:
    """Reject text experiments on Apple PPO and titles on Play listing experiments."""
    if not isinstance(surface, str) or surface not in SURFACES[platform]:
        raise Invalid("Choose a supported store review or experiment surface")
    if not isinstance(test_fields, list) or len(test_fields) > 10 or any(not isinstance(v, str) for v in test_fields):
        raise Invalid("Use up to ten named test fields")
    if len(test_fields) != len(set(test_fields)):
        raise Invalid("Test fields cannot repeat")
    unsupported = sorted(set(test_fields) - SURFACES[platform][surface])
    return [issue("test_fields", "UNSUPPORTED_SURFACE", "This surface cannot test: " + ", ".join(unsupported) + ". Select a supported surface or prepare a manual metadata review.")] if unsupported else []
