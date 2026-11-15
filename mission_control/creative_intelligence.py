"""Recommend creative patterns from WMM's validated app-scoped research evidence."""

from collections.abc import Iterator, Mapping
from fractions import Fraction

from .common import Invalid, iso_time

SHORTLIST_LIMIT = 3


def _strength(source, proof) -> Fraction:
    """Use an exact creator-relative ratio only for qualified evidence."""
    median = proof.get("median")
    if proof["qualification"] == "QUALIFIED_BY_REPORTED_COUNTS" and median:
        return Fraction(source["views"] * median["denominator"], median["numerator"])
    return Fraction(0)


def _rank(entry, row):
    """Accept relevant references while leaving owned media and denied sources separate."""
    if entry["kind"] != "REFERENCE" or entry["relevance"] != "MATCH" or entry["rights"] == "DENIED":
        return None
    source = entry["candidate"]
    proof = row["qualification"]
    if row["candidate_id"] != source["post_id"]:
        raise Invalid("Selection evidence does not match saved source")
    qualified = proof["qualification"] == "QUALIFIED_BY_REPORTED_COUNTS"
    score = (
        not qualified,
        -_strength(source, proof),
        -iso_time(source["published_at"]).timestamp(),
        source["platform"],
        source["post_id"],
    )
    return score, source, proof, qualified


def _rows(submission: Mapping[str, object], result: Mapping[str, object]) -> Iterator[tuple[object, object]]:
    """Match the two integrity-checked saved arrays without silently truncating either."""
    candidates, evaluated = submission["candidates"], result["items"]
    if not isinstance(candidates, list) or not isinstance(evaluated, list):
        raise Invalid("Saved creative research evidence has an invalid shape")
    return zip(candidates, evaluated, strict=True)


def creative_shortlist(
    submission: Mapping[str, object] | None, result: Mapping[str, object] | None
) -> list[dict[str, str]]:
    """Rank reported app fit without treating missing evidence as viral proof."""
    if not submission or not result:
        return []
    ranked = [_rank(entry, row) for entry, row in _rows(submission, result)]
    shortlist: list[dict[str, str]] = []
    creators = set()
    for _, source, proof, qualified in sorted((pick for pick in ranked if pick is not None), key=lambda row: row[0]):
        creator = (source["platform"], source["creator_id"].casefold())
        if creator in creators:
            continue
        creators.add(creator)
        shortlist.append(
            dict(
                platform=source["platform"],
                post_id=source["post_id"],
                candidate_hash=proof["candidate_hash"],
                tier="VIRAL_BY_REPORTED_COUNTS" if qualified else "PROMISING_PATTERN",
                reason="APP_FIT_AND_VIRAL_THRESHOLDS" if qualified else "APP_FIT_NOT_VIRAL_QUALIFIED",
                next_action="REVIEW_SOURCE" if qualified else "INSPECT_PATTERN_ONLY",
                adaptation="ORIGINAL_ASSETS_ONLY",
            )
        )
        if len(shortlist) == SHORTLIST_LIMIT:
            break
    return shortlist
