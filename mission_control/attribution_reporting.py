"""Descriptive channel-separated observations; overlap, unsigned values and history stay explicit."""
from collections import defaultdict
from .common import digest


def interpretation(observation,versions,conflict):
    """Map only an explicit unsigned value, never derive revenue or verified activation."""
    if conflict:return {"status":"CONFLICT_UNKNOWN","label":None,"verification":"UNSIGNED_OBSERVATION"}
    unsigned=observation.get("unsigned",{})
    rows=versions["fine"] if unsigned.get("conversion_value") is not None else versions["coarse"]
    value=unsigned.get("conversion_value") if unsigned.get("conversion_value") is not None else unsigned.get("coarse_conversion_value")
    label=next((row["label"] for row in rows if row["value"]==value),None)
    return {"status":"MAPPED_UNSIGNED" if label else "UNAVAILABLE_OR_UNMAPPED","label":label,
            "verification":"UNSIGNED_OBSERVATION"}


def group_record(rows,maps):
    """Deduplicate signed identity, and make conversion conflicts visible rather than overwriting."""
    first=rows[0];obs=first["data"]["observation"]
    conflict=len({digest(r["data"]["observation"].get("unsigned")) for r in rows})>1
    version=maps.get((first["map_id"],first["map_version"]))
    mapped=interpretation(obs,version["data"],conflict) if version else None
    historical=all(r["imported"] for r in rows)
    return {"identity":obs["identity"],"channel":obs["channel"],"environment":obs["environment"],
            "postback_id":obs.get("postback_id"),"observations":len(rows),"unsigned_conflict":conflict,
            "mapping":mapped,"historical":historical,
            "verification":"HISTORICAL_ASSERTION_NOT_REVERIFIED" if historical else first["data"]["verification"],
            "conversion_type":obs.get("conversion_type"),"sequence":obs.get("sequence"),
            "did_win":obs.get("did_win"),"attribution":obs.get("attribution"),
            "new_install_candidate":bool(obs.get("new_install_candidate")) and not historical,
            "overlap_status":"UNRESOLVED"}


def report(receipts,maps):
    """Never sum SKAN, AAK and AdServices into a combined install total."""
    groups=defaultdict(list)
    for row in receipts:groups[row["identity"]].append(row)
    index={(m["id"],m["version"]):m for m in maps}
    records=[group_record(rows,index) for rows in groups.values()]
    channels=[]
    for channel in ("SKAdNetwork","AdAttributionKit","AdServices"):
        for environment in ("Production","Development"):
            selected=[r for r in records if r["channel"]==channel and r["environment"]==environment]
            channels.append({"channel":channel,"environment":environment,"unique_observations":len(selected),
                             "current_download_candidates":sum(r["new_install_candidate"] for r in selected),
                             "unsigned_conflicts":sum(r["unsigned_conflict"] for r in selected),
                             "historical_observations":sum(r["historical"] for r in selected)})
    return {"channels":channels,"records":records,"combined_installs":None,"attributed_revenue":None,
            "overlap_status":"UNRESOLVED","actual_device_delivery":"NOT_VERIFIED",
            "warning":"Unsigned mapping labels are descriptive. No verified activation, cash or cross-channel deduplication is inferred."}
