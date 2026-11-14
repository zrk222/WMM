"""Owner-report guidance from retained pause evidence only."""

from collections.abc import Iterable, Mapping


def pause_guidance(receipts: Iterable[Mapping[str, object]]) -> str | None:
    unconfirmed = False
    for receipt in receipts:
        readback = receipt.get("pause_readback")
        effective = readback.get("effective_status") if isinstance(readback, Mapping) else None
        if effective == "ACTIVE":
            return (
                "The saved pause read showed Meta reporting active delivery. Verify current status for the exact campaign "
                "before interpreting results; do not retry the pause from this report."
            )
        if receipt["status"] == "PAUSED_campaign" and effective != "PAUSED":
            unconfirmed = True
    if unconfirmed:
        return (
            "The saved records do not confirm an effective Meta pause. Check the exact campaign in Meta "
            "before interpreting results; do not retry the pause from this report."
        )
    return None
