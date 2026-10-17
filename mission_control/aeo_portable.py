"""Passive AEO migration; outer hashes never authenticate imported source assertions."""
import re
from .common import digest, iso_time
from .aeo_contract import fields, require, sha
from .aeo_workflows import rows, validate_data, insert
from .acquisition_portable import historical


def export_aeo(db, app_id):
    """Export immutable app-owned history, without derived currentness."""
    return rows(db,app_id)


def restore_aeo(db, app_id, values):
    """Validate every assertion in the caller transaction; old snapshots remain readable."""
    if values is None:
        return
    require(isinstance(values,list) and len(values) <= 500)
    seen=set()
    for row in values:
        validate_row(db,app_id,row)
        require(row["id"] not in seen, "Duplicate AEO observation.")
        seen.add(row["id"])
        insert(db,row,"IMPORTED_ASSERTION")


def validate_row(db, app_id, row):
    """Recomputed hashes, closed metadata and exact historical intent joins are mandatory."""
    fields(row,"app_id id data hash created origin")
    require(row["app_id"] == app_id)
    require(isinstance(row["id"],str) and bool(re.fullmatch("[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",row["id"])))
    require(row["origin"] in ("LOCAL_OBSERVATION","IMPORTED_ASSERTION"))
    validate_data(row["data"],app_id)
    require(sha(row["hash"]) == digest(row["data"]))
    require(row["created"] == row["data"]["observed_at"])
    iso_time(row["created"])
    bound=row["data"]["binding"]
    if bound["intent"] is not None:
        intent=bound["intent"]
        fields(intent,"app_id id version data hash created")
        retained=historical(db,"acquisition_intents",app_id,intent["id"],intent["hash"])
        require(retained == intent, "Imported AEO intent history changed.")
        require(intent["data"]["app_hash"] == bound["app_hash"])
        require(intent["data"]["definition"]["page_url"] == bound["target"])
