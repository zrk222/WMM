"""Exact sanitized history replay; discarded JWS and local read authority cannot be restored."""
import re
import time
from .common import Invalid, canonical, digest, iso_time
from .storekit_contract import declaration, integer, canonical_uuid, text, date, scope, transaction, TRANSACTION_FIELDS, NOTIFICATION_FIELDS
from .storekit_sources import checked
from .storekit_ingestion import receipt

SOURCE_FIELDS={"id","data","hash","version","status","imported","created"}
RECEIPT_FIELDS={"app_id","id","source_id","data","hash","status","imported","created"}
FAILURE_FIELDS={"app_id","id","source_id","data","hash","imported","created"}
DATA_FIELDS={"notification","content_sha256","body_sha256","source_hash","source_version","verified_at","verification"}
TX_MAP={"transaction_id":"transactionId","original_transaction_id":"originalTransactionId","product_id":"productId",
        "purchase_date":"purchaseDate","signed_date":"signedDate","expires_date":"expiresDate","ownership":"inAppOwnershipType",
        "price_milliunits":"price","currency":"currency","quantity":"quantity","transaction_type":"type",
        "revocation_type":"revocationType","revocation_percentage_milliunits":"revocationPercentage","revocation_date":"revocationDate"}


def require(value,message):
    """Keep all replay rejection atomic and explicit."""
    if not value:raise Invalid("StoreKit history: "+message)


def hashed(row,fields):
    """Require a closed schema and hash rather than smuggling untrusted private fields."""
    require(isinstance(row,dict) and set(row)==fields,"row schema differs")
    data=row["data"]
    require(isinstance(data,dict) and digest(data)==row["hash"],"data hash differs")
    iso_time(row["created"])
    require(canonical_uuid(row["id"])==row["id"],"noncanonical row UUID")
    require(type(row["imported"]) is int and row["imported"] in (0,1),"import flag invalid")
    return data


def config_data(data):
    """Validate public identity without restoring the original certificate-read grant."""
    require(set(data)=={"bundle_id","app_apple_id","environment"},"private/source fields are forbidden")
    normalized=declaration({**data,"confirm_read":True})
    require(normalized==data,"source values differ from typed public declaration")


def source_rows(rows):
    """Validate bounded source histories while never creating a current source."""
    result={}
    for row in rows:
        data=hashed(row,SOURCE_FIELDS);config_data(data)
        integer(row["version"],"source version",high=1000000)
        require(row["status"] in ("ACTIVE","DISCONNECTED","IMPORTED_HISTORY"),"source status invalid")
        require(row["id"] not in result,"duplicate source")
        result[row["id"]]=row
    return result


def notification_data(data,config):
    """Revalidate every sanitized fact; this is shape validation, not signature verification."""
    require(isinstance(data,dict) and set(data)==NOTIFICATION_FIELDS,"notification fields differ")
    require(canonical_uuid(data["notification_id"])==data["notification_id"],"notification UUID differs")
    text(data["notification_type"],"notification type",80,r"[A-Z0-9_]+")
    if data["subtype"] is not None:text(data["subtype"],"notification subtype",80,r"[A-Z0-9_]+")
    date(data["signed_date"],"notification signed date",time.time())
    scope({"bundleId":data["bundle_id"],"appAppleId":data["app_apple_id"],"environment":data["environment"]},config)
    tx=data["transaction"]
    if tx is not None:transaction_data(tx,config)
    from .storekit_contract import TRANSACTION_TYPES
    require(tx is not None or data["notification_type"] not in TRANSACTION_TYPES,"required transaction missing")


def transaction_data(data,config):
    """Replay only exact typed fields; preserve absent prices and ownership as unknown."""
    require(isinstance(data,dict) and set(data)==TRANSACTION_FIELDS,"transaction fields differ")
    require(type(data["advanced_commerce"]) is bool,"advanced commerce flag invalid")
    raw={wire:data[key] for key,wire in TX_MAP.items() if data[key] is not None}
    raw.update(bundleId=config["bundle_id"],environment=config["environment"])
    if data["advanced_commerce"]:raw["advancedCommerceInfo"]={}
    require(transaction(raw,config,time.time())==data,"transaction replay differs")


def receipt_rows(rows,app,sources):
    """Require exact app/source/content bindings and declared native or historical provenance."""
    result={}
    for row in rows:
        data=hashed(row,RECEIPT_FIELDS)
        require(set(data)==DATA_FIELDS and row["app_id"]==app,"receipt schema/app differs")
        require(row["source_id"] in sources,"source missing")
        src=sources[row["source_id"]]
        require(data["source_hash"]==src["hash"],"source hash differs")
        integer(data["source_version"],"receipt source version",high=src["version"])
        notification_data(data["notification"],src["data"])
        require(row["id"]==data["notification"]["notification_id"],"notification identity differs")
        require(data["content_sha256"]==digest(data["notification"]),"content hash differs")
        require(bool(re.fullmatch(r"[a-f0-9]{64}",str(data["body_sha256"]))),"body hash invalid")
        iso_time(data["verified_at"])
        require(data["verification"] in ("NATIVE_APPLE_CHAIN_ES256_AND_REVOCATION","HISTORICAL_ASSERTION_NOT_REVERIFIED"),"verification label invalid")
        require(row["status"] in ("VERIFIED","IMPORTED_HISTORY"),"receipt state invalid")
        require(row["id"] not in result,"duplicate receipt")
        result[row["id"]]=row
    return result


def failure_rows(rows,app,sources):
    """Accept redacted failure metadata only; never raw body or claimed unverified output."""
    seen=set()
    for row in rows:
        data=hashed(row,FAILURE_FIELDS)
        require(row["app_id"]==app and row["source_id"] in sources,"failure source/app differs")
        require(set(data)=={"body_sha256","code","retry"},"failure fields differ")
        require(data["body_sha256"] is None or re.fullmatch(r"[a-f0-9]{64}",str(data["body_sha256"])),"failure hash invalid")
        require(data["code"]=="VERIFICATION_FAILED" and data["retry"]=="RESELECT_ORIGINAL_FILE","failure code differs")
        require(row["id"] not in seen,"duplicate failure")
        seen.add(row["id"])


def validate(data,app):
    """Require finite historical lists and all joins before touching the database."""
    require(isinstance(data,dict) and set(data)=={"schema","app_id","sources","receipts","failures"},"snapshot schema differs")
    require(data["schema"]=="growth.storekit-history.v1" and data["app_id"]==app,"snapshot identity differs")
    for key,cap in (("sources",100),("receipts",10000),("failures",1000)):
        require(isinstance(data[key],list) and len(data[key])<=cap,"snapshot list exceeds bound")
    sources=source_rows(data["sources"])
    receipt_rows(data["receipts"],app,sources);failure_rows(data["failures"],app,sources)
    return data


def export_storekit(db,app):
    """Export exact public history with no read grant, role or signature body."""
    sources=[{key:checked(row)[key] for key in SOURCE_FIELDS} for row in db.execute("SELECT * FROM storekit_sources WHERE app_id=?",(app,))]
    receipts=[receipt(row) for row in db.execute("SELECT * FROM storekit_receipts WHERE app_id=?",(app,))]
    failures=[checked(row) for row in db.execute("SELECT * FROM storekit_failures WHERE app_id=?",(app,))]
    data={"schema":"growth.storekit-history.v1","app_id":app,"sources":sources,"receipts":receipts,"failures":failures}
    return validate(data,app)


def restore_storekit(db,app,data):
    """Restore passive sanitized assertions within the caller's single SQL transaction."""
    if data is None:return
    validate(data,app)
    for row in data["sources"]:
        scope_key=digest({"bundle_id":row["data"]["bundle_id"],"environment":row["data"]["environment"]})
        db.execute("INSERT INTO storekit_sources VALUES(?,?,?,?,?,?,?,?,?,?)",(app,row["id"],canonical(row["data"]),row["hash"],row["version"],"IMPORTED_HISTORY",1,scope_key,0,row["created"]))
    for row in data["receipts"]:
        value={**row["data"],"verification":"HISTORICAL_ASSERTION_NOT_REVERIFIED"}
        db.execute("INSERT INTO storekit_receipts VALUES(?,?,?,?,?,?,?,?)",(app,row["id"],row["source_id"],canonical(value),digest(value),"IMPORTED_HISTORY",1,row["created"]))
    for row in data["failures"]:
        db.execute("INSERT INTO storekit_failures VALUES(?,?,?,?,?,?,?)",(app,row["id"],row["source_id"],canonical(row["data"]),row["hash"],1,row["created"]))
