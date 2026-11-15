"""Map pinned rea-video JSON output to non-authorizing WMM observations."""

import math
from collections.abc import Mapping
from typing import Any

from .common import Invalid
from .creative_toolchain import handoff

REA_VIDEO_REVISION = "b08faf2eb53690fc92ddf94576a8c7c3a4a87f89"


def milliseconds(value: object) -> int:
    """Convert a bounded time in seconds without accepting nonfinite values."""
    if type(value) not in (int, float):
        raise Invalid("Use numeric rea-video timestamps")
    if not isinstance(value, (int, float)) or not 0 <= value <= 180 or not math.isfinite(value):
        raise Invalid("Use rea-video timestamps within a three-minute clip")
    return round(value * 1000)


def observed_shot(shot: object) -> dict[str, Any]:
    """Import the boundary observation without adopting inferred labels or instructions."""
    if not isinstance(shot, dict):
        raise Invalid("rea-video returned an invalid shot")
    return {
        "start_ms": milliseconds(shot.get("start")),
        "end_ms": milliseconds(shot.get("end")),
        "text": "Shot boundary detected by rea-video.",
    }


def analysis_handoff(
    breakdown: Mapping[str, Any], binding: Mapping[str, Any], measured_duration_ms: int, analyzer_sha256: str
) -> dict[str, Any]:
    """Import only shot boundaries and check them against locally measured media duration."""
    source, shots = breakdown.get("source"), breakdown.get("shots")
    if not isinstance(source, dict) or not isinstance(shots, list) or not 1 <= len(shots) <= 60:
        raise Invalid("Provide a rea-video breakdown with up to 60 shots")
    if type(measured_duration_ms) is not int or abs(milliseconds(source.get("duration")) - measured_duration_ms) > 50:
        raise Invalid("The breakdown duration does not match the selected clip")
    return handoff(
        "rea-video",
        binding,
        {
            "duration_ms": measured_duration_ms,
            "observed_beats": [observed_shot(shot) for shot in shots],
            "interpretation": "Detected cuts only; review the clip before inferring hooks, intent, or performance.",
            "analyzer_revision": REA_VIDEO_REVISION,
            "analyzer_sha256": analyzer_sha256,
        },
    )
