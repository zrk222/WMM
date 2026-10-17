"""Closed sanitized attribution replay; imported rows never regain current read/signature authority."""
import re
from .common import Invalid,canonical,digest,iso_time
from . import attribution_contract as contract
from .attribution_sources import declaration as source_data,checked,PUBLIC_SOURCE
from .attribution_maps import declaration as map_data
from . import attribution_skan,attribution_aak,attribution_adservices

SCHEMA="growth.attribution-history.v1"
MAP_FIELDS={"app_id","id","version","data","hash","imported","created"}
RECEIPT_FIELDS={"app_id","id","source_id","map_id","map_version","identity","data","hash","imported","created"}
FAILURE_FIELDS={"app_id","id","source_id","data","hash","imported","created"}
READ_FIELDS=FAILURE_FIELDS|{"status"}
RECEIPT_DATA={"observation","claim_sha256","body_sha256","source_hash","source_version","map_hash","received_at","verification"}


def require(value,message):
    """Every replay validation fails before committing any app or row."""
    if not value:raise Invalid("Attribution history: "+message)


def hash_text(value):
    """Reject arbitrary provider payloads disguised as digest fields."""
    require(isinstance(value,str) and re.fullmatch(r"[a-f0-9]{64}",value),"digest is invalid")


def row_data(row,fields,app,hashed_id=False):
    """Validate closed row metadata and immutable finite content hash."""
    require(isinstance(row,dict) and set(row)==fields,"row schema differs")
    require(row["app_id"]==app,"foreign app")
    require(type(row["imported"]) is int and row["imported"] in (0,1),"import flag differs")
    if hashed_id:hash_text(row["id"])
    else:contract.postback_id(row["id"])
    iso_time(row["created"])
    require(isinstance(row["data"],dict) and digest(row["data"])==row["hash"],"data hash differs")
    return row["data"]


def native_observation(obs,config):
    """Recompute typed normalized meaning only; this is not signature reverification."""
    require(isinstance(obs,dict),"observation missing")
    signed,unsigned=obs.get("signed"),obs.get("unsigned")
    require(isinstance(signed,dict) and isinstance(unsigned,dict),"native claims missing")
    wire={**signed}
    if obs.get("channel")=="SKAdNetwork":
        version=obs.get("version")
        require(version in attribution_skan.VERSIONS,"unsupported SKAN version")
        wire["attribution-signature"]="HISTORICAL"
        if version=="1.0":wire["version"]="1.0"
        converted=wire_conversions(unsigned)
        wire.update(converted)
        attribution_skan.validate(wire,version,int(config["app_apple_id"]),config["environment"])
        sequence=wire.get("postback-sequence-index",0)
        normalized=contract.conversions(converted,sequence)
        require(set(unsigned)==set(normalized),"unsigned fields differ")
        conversion="unavailable" if version=="1.0" else "redownload" if wire["redownload"] else "download"
        expected=contract.result("SKAdNetwork",version,attribution_skan.signed_fields(wire,version),
                 normalized,int(config["app_apple_id"]),config["environment"],wire["transaction-id"],
                 conversion,sequence,wire.get("did-win",True))
    else:
        from .attribution_keys import aak_key
        require(obs.get("channel")=="AdAttributionKit","native channel differs")
        aak_key(obs.get("version"),config["environment"])
        attribution_aak.validate_payload(signed,int(config["app_apple_id"]),config["environment"])
        sequence=signed["postback-sequence-index"]
        converted=wire_conversions(unsigned)
        converted.update({"country-code":unsigned.get("country_code"),"ad-interaction-type":unsigned.get("ad_interaction_type")})
        normalized=attribution_aak.outer_observations(converted,sequence)
        require(set(unsigned)==set(normalized),"unsigned fields differ")
        expected=contract.result("AdAttributionKit",obs["version"],signed,normalized,int(config["app_apple_id"]),
                 config["environment"],signed["postback-identifier"],signed["conversion-type"],sequence,signed["did-win"])
    require(obs==expected,"native normalized meaning differs")


def wire_conversions(unsigned):
    """Never turn a missing or null conversion into zero while replaying history."""
    result={}
    if unsigned.get("conversion_value") is not None:result["conversion-value"]=unsigned["conversion_value"]
    if unsigned.get("coarse_conversion_value") is not None:result["coarse-conversion-value"]=unsigned["coarse_conversion_value"]
    return result


def sources_data(rows,app):
    """Source declarations restore without owner memberships or read grants."""
    result={}
    for row in rows:
        data=row_data(row,PUBLIC_SOURCE,app)
        require(source_data({**data,"confirm_read":True})==data,"source declaration differs")
        contract.integer(row["version"],1,1000000)
        require(row["status"] in ("ACTIVE","DISCONNECTED","IMPORTED_HISTORY"),"source status differs")
        require(row["id"] not in result,"duplicate source")
        result[row["id"]]=row
    return result


def maps_data(rows,app):
    """Retain every original immutable mapping, including declared effective time."""
    result={}
    for row in rows:
        data=row_data(row,MAP_FIELDS,app)
        require(map_data(data)==data,"mapping declaration differs")
        contract.integer(row["version"],1,1000000)
        key=(row["id"],row["version"])
        require(key not in result,"duplicate mapping version")
        result[key]=row
    return result


def receipt_data(row,app,sources,maps,reads):
    """Require exact source/map joins and reconstruct all sanitized facts."""
    data=row_data(row,RECEIPT_FIELDS,app,True)
    require(set(data)==RECEIPT_DATA and row["source_id"] in sources,"receipt schema/source differs")
    src=sources[row["source_id"]]
    require(data["source_hash"]==src["hash"],"source hash differs")
    contract.integer(data["source_version"],1,src["version"])
    hash_text(data["body_sha256"]);iso_time(data["received_at"])
    obs=data["observation"]
    require(isinstance(obs,dict) and obs.get("channel")==src["data"]["channel"],"channel differs")
    if obs["channel"]=="AdServices":
        require(row["map_id"] is None and row["map_version"] is None and data["map_hash"] is None,"AdServices mapping forbidden")
        require(data["body_sha256"] in reads and reads[data["body_sha256"]]["source_id"]==src["id"],"AdServices read missing")
        require(attribution_adservices.observation(obs.get("facts"),src["data"],data["body_sha256"])==obs,"AdServices meaning differs")
        require(data["verification"] in ("API_RETRIEVED_DECLARED_SDK_SCOPE","HISTORICAL_ASSERTION_NOT_REVERIFIED"),"API provenance differs")
    else:
        native_observation(obs,src["data"])
        selected=maps.get((row["map_id"],row["map_version"]))
        require(selected and selected["hash"]==data["map_hash"],"mapping join/hash differs")
        require(selected["data"]["channel"]==obs["channel"] and selected["data"]["sequence"]==obs["sequence"],"mapping scope differs")
        require(iso_time(selected["data"]["effective_at"])<=iso_time(data["received_at"]),"mapping not yet effective")
        require(data["verification"] in ("NATIVE_APPLE_SIGNATURE","HISTORICAL_ASSERTION_NOT_REVERIFIED"),"native provenance differs")
    require(row["identity"]==obs["identity"],"identity differs")
    require(row["id"]==digest({"identity":obs["identity"],"unsigned":obs.get("unsigned")}),"receipt identity differs")
    require(data["claim_sha256"]==obs.get("signed_sha256",digest(obs)),"claim hash differs")


def read_data(rows,app,sources):
    """Digest-only read history cannot resume a request or recreate its token."""
    result={}
    for row in rows:
        data=row_data(row,READ_FIELDS,app,True)
        require(set(data)=={"digest","obtained_at","source_hash","source_version","status"},"read fields differ")
        require(row["source_id"] in sources and sources[row["source_id"]]["data"]["channel"]=="AdServices","read source differs")
        src=sources[row["source_id"]]
        require(data["digest"]==row["id"] and data["source_hash"]==src["hash"],"read binding differs")
        contract.integer(data["source_version"],1,src["version"])
        iso_time(data["obtained_at"])
        require(row["status"]==data["status"] and row["status"] in ("PENDING","SUCCEEDED","FAILED"),"read status differs")
        require(row["id"] not in result,"duplicate read")
        result[row["id"]]=row
    return result


def failures_data(rows,app,sources):
    """Retain redacted recovery metadata only; reject raw messages, JWS or contacts."""
    seen=set()
    for row in rows:
        data=row_data(row,FAILURE_FIELDS,app)
        require(row["source_id"] in sources,"failure source missing")
        require(set(data)=={"body_sha256","code","retry"},"failure fields differ")
        if data["body_sha256"] is not None:hash_text(data["body_sha256"])
        require(data["code"] in ("VERIFICATION_FAILED","ADSERVICES_READ_FAILED"),"failure code differs")
        require(data["retry"]=="RESELECT_FRESH_INPUT" and row["id"] not in seen,"failure identity/retry differs")
        seen.add(row["id"])


def validate(data,app):
    """Check all closed joins and bounds before the caller's atomic restore."""
    require(isinstance(data,dict) and set(data)=={"schema","app_id","sources","maps","receipts","failures","reads"},"snapshot schema differs")
    require(data["schema"]==SCHEMA and data["app_id"]==app,"snapshot identity differs")
    for key,cap in (("sources",100),("maps",100),("receipts",10000),("failures",1000),("reads",10000)):
        require(isinstance(data[key],list) and len(data[key])<=cap,"snapshot list exceeds limit")
    require(len(data["receipts"])+len(data["reads"])<=10000,"combined history exceeds limit")
    sources=sources_data(data["sources"],app);maps=maps_data(data["maps"],app);reads=read_data(data["reads"],app,sources)
    seen=set();claims={}
    for row in data["receipts"]:
        receipt_data(row,app,sources,maps,reads)
        require(row["id"] not in seen,"duplicate receipt")
        prior=claims.setdefault(row["identity"],row["data"]["claim_sha256"])
        require(prior==row["data"]["claim_sha256"],"conflicting signed identity")
        seen.add(row["id"])
    failures_data(data["failures"],app,sources)
    return data


def export_attribution(db,app):
    """Export sanitized history only, never raw postbacks, tokens or authority."""
    result={"schema":SCHEMA,"app_id":app}
    for name in ("sources","maps","receipts","failures","reads"):
        rows=[checked(r) for r in db.execute("SELECT * FROM attribution_"+name+" WHERE app_id=?",(app,))]
        result[name]=[{k:r[k] for k in PUBLIC_SOURCE} for r in rows] if name=="sources" else rows
    return validate(result,app)


def restore_attribution(db,app,data):
    """Restore passive assertions within the caller's existing SQL transaction."""
    if data is None:return
    validate(data,app)
    for row in data["sources"]:
        config=row["data"];key=digest({k:config[k] for k in ("app_apple_id","channel","environment")})
        db.execute("INSERT INTO attribution_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (app,row["id"],canonical(config),row["hash"],row["version"],"IMPORTED_HISTORY",1,key,0,row["created"]))
    for row in data["maps"]:
        db.execute("INSERT INTO attribution_maps VALUES(?,?,?,?,?,?,?)",
                   (app,row["id"],row["version"],canonical(row["data"]),row["hash"],1,row["created"]))
    for row in data["reads"]:
        db.execute("INSERT INTO attribution_reads VALUES(?,?,?,?,?,?,?,?)",
                   (app,row["id"],row["source_id"],canonical(row["data"]),row["hash"],row["status"],1,row["created"]))
    for row in data["receipts"]:
        value={**row["data"],"verification":"HISTORICAL_ASSERTION_NOT_REVERIFIED"}
        db.execute("INSERT INTO attribution_receipts VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (app,row["id"],row["source_id"],row["map_id"],row["map_version"],row["identity"],canonical(value),digest(value),1,row["created"]))
    for row in data["failures"]:
        db.execute("INSERT INTO attribution_failures VALUES(?,?,?,?,?,?,?)",
                   (app,row["id"],row["source_id"],canonical(row["data"]),row["hash"],1,row["created"]))
