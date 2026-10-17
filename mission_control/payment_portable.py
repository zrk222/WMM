"""Strict sanitized payment history replay; never transfers endpoint or key authority."""
import re
from .common import Invalid, canonical, digest, iso_time
from .payment_signature import object_id
from .signed_payments import checked, integer, TERMINAL

SOURCE_FIELDS={"id","data","hash","version","status","imported","created"}
RECEIPT_FIELDS={"app_id","event_id","source_id","data","hash","status","imported","created"}
ATTEMPT_FIELDS={"app_id","event_id","version","data","hash","created"}
EFFECT_FIELDS={"account_id","livemode","object_id","kind","charge_id","balance_id","currency","gross_minor","fee_minor","net_minor","occurred_at","attribution"}
STATUSES=TERMINAL|{"PENDING","UNSUPPORTED","FAILED","FX_RECONCILIATION_REQUIRED"}


def require(value,message):
    """Make semantic replay failures atomic input errors, never false verification."""
    if not value:raise Invalid("Payment snapshot: "+message)


def hashed(row,fields):
    """Require an exact public schema and the current data hash."""
    require(isinstance(row,dict) and set(row)==fields,"record schema differs")
    require(isinstance(row["data"],dict) and digest(row["data"])==row["hash"],"record hash differs")
    iso_time(row["created"])
    return row["data"]


def uuid_id(value):
    """Reject injected or colliding source identities before SQL replay."""
    require(isinstance(value,str) and re.fullmatch(r"[a-f0-9-]{36}",value),"source identity invalid")
    return value


def config_data(data):
    """Validate sanitized public config without creating or inventing a credential."""
    require(set(data)=={"account_id","livemode","api_version"},"source fields differ")
    object_id(data["account_id"],"acct")
    require(type(data["livemode"]) is bool,"source mode invalid")
    require(isinstance(data["api_version"],str) and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}(?:[.][a-z]+)?",data["api_version"]),"API version invalid")


def effect_data(data):
    """Require actual-cash arithmetic and explicit unallocated attribution."""
    require(isinstance(data,dict) and set(data)==EFFECT_FIELDS,"cash effect schema differs")
    object_id(data["account_id"],"acct");object_id(data["charge_id"],"ch");object_id(data["balance_id"],"txn")
    require(data["kind"] in ("charge","refund","refund_reversal"),"cash kind invalid")
    object_id(data["object_id"],"ch" if data["kind"]=="charge" else "re")
    require(type(data["livemode"]) is bool and data["attribution"]=="UNALLOCATED","cash authority or attribution invalid")
    require(isinstance(data["currency"],str) and re.fullmatch(r"[A-Z]{3}",data["currency"]),"currency invalid")
    gross=integer(data["gross_minor"],"gross",True);fee=integer(data["fee_minor"],"fee",True);net=integer(data["net_minor"],"net",True)
    require(net==gross-fee and (gross<0 if data["kind"]=="refund" else gross>0),"cash arithmetic differs")
    if data["kind"]=="charge":require(data["object_id"]==data["charge_id"],"charge scope differs")
    iso_time(data["occurred_at"])


def source_records(items):
    """Validate unique safe source metadata; active status never survives restore."""
    result={}
    for row in items:
        data=hashed(row,SOURCE_FIELDS);sid=uuid_id(row["id"]);config_data(data)
        require(sid not in result,"duplicate source")
        require(type(row["version"]) is int and row["version"]>=1,"source version invalid")
        require(row["status"] in ("ACTIVE","DISCONNECTED","CLEANUP_REQUIRED","IMPORTED_HISTORY"),"source state invalid")
        require(row["imported"] in (0,1),"source import flag invalid")
        result[sid]=row
    return result


def receipt_data(row,app_id,sources):
    """Validate closed sanitized receipt schema and exact declared source binding."""
    data=hashed(row,RECEIPT_FIELDS)
    fields={"event_id","event_type","event_created","livemode","body_sha256","content_sha256","object_id","charge_id","candidate","source_hash","source_version","signature_timestamp","verification","received_at"}
    require(set(data)==fields and row["app_id"]==app_id,"receipt schema or app differs")
    require(row["source_id"] in sources,"receipt source missing");src=sources[row["source_id"]]
    require(data["source_hash"]==src["hash"] and data["source_version"]==1,"receipt source differs")
    object_id(data["event_id"],"evt");require(row["event_id"]==data["event_id"],"receipt identity differs")
    require(data["livemode"] is src["data"]["livemode"],"receipt mode differs")
    require(type(data["candidate"]) is bool,"candidate flag invalid")
    receipt_time_hashes(data)
    from .payment_signature import SUPPORTED
    require(data["candidate"]==(data["event_type"] in SUPPORTED),"candidate type differs")
    if data["candidate"]:
        object_id(data["object_id"],"ch" if data["event_type"]=="charge.succeeded" else "re")
        object_id(data["charge_id"],"ch")
    else:require(data["object_id"] is None and data["charge_id"] is None,"unsupported event contains cash identity")
    require(row["status"] in STATUSES and row["imported"] in (0,1),"receipt state invalid")
    return data


def attempt_data(row,app_id,receipt,src,expected):
    """Validate contiguous attempt order, receipt provenance and source/account joins."""
    data=hashed(row,ATTEMPT_FIELDS)
    fields={"status","effects","receipt_hash","source_id","source_version","actor","role_version","read_at","authority"}
    require(set(data) in (fields,fields|{"error"}),"attempt schema differs")
    require(row["app_id"]==app_id and row["event_id"]==receipt["event_id"] and row["version"]==expected,"attempt order/scope differs")
    require(data["receipt_hash"]==receipt["hash"] and data["source_id"]==src["id"],"attempt receipt differs")
    require(data["source_version"]==1 and type(data["role_version"]) is int and data["role_version"]>=1,"attempt role/source version invalid")
    require(isinstance(data["actor"],str) and re.fullmatch(r"github:[0-9]+",data["actor"]),"attempt principal invalid")
    require(data["authority"]=="READ_ONLY_CONFIGURED_KEY" and data["status"] in STATUSES-{"UNSUPPORTED"},"attempt outcome invalid")
    require(iso_time(data["read_at"])>=iso_time(receipt["data"]["received_at"]),"attempt precedes receipt")
    attempt_effects(data,receipt,src)
    return data


def bound_effect(effect,receipt,src):
    """Require every observed effect to match exact receipt object and source account."""
    effect_data(effect)
    require(effect["account_id"]==src["data"]["account_id"] and effect["livemode"] is src["data"]["livemode"],"cash account differs")
    require(effect["object_id"]==receipt["data"]["object_id"] and effect["charge_id"]==receipt["data"]["charge_id"],"cash object differs")
    require((effect["kind"]=="charge")==(receipt["data"]["event_type"]=="charge.succeeded"),"cash type differs")


def paired_effects(effects):
    """A failed refund has exactly the same debit amount and compensating credit."""
    require({e["kind"] for e in effects}=={"refund","refund_reversal"},"failed-refund pair differs")
    require(len({e["balance_id"] for e in effects})==2,"failed-refund balances duplicate")
    require(effects[0]["gross_minor"]==-effects[1]["gross_minor"] and effects[0]["currency"]==effects[1]["currency"],"failed-refund cash pair differs")


def validate_payload(payload,app_id):
    """Validate bounded source, receipt, attempt and effect histories before any insert."""
    require(isinstance(payload,dict) and set(payload)=={"sources","receipts","attempts","effects","authority"},"payload schema differs")
    require(payload["authority"]=="HISTORY_ONLY_NO_ENDPOINT_KEYS_OR_ROLES","snapshot authority differs")
    limits={"sources":100,"receipts":10000,"attempts":100000,"effects":20000}
    for key,maximum in limits.items():require(isinstance(payload[key],list) and len(payload[key])<=maximum,"collection exceeds bound")
    sources=source_records(payload["sources"]);receipts={}
    for row in payload["receipts"]:
        receipt_data(row,app_id,sources);require(row["event_id"] not in receipts,"duplicate receipt");receipts[row["event_id"]]=row
    return sources,receipts


def history_effects(payload,app_id,sources,receipts):
    """Reconstruct retained economic evidence from contiguous validated attempt history."""
    counts={};latest={};observed={}
    for row in payload["attempts"]:
        eid=row["event_id"];require(eid in receipts,"attempt receipt missing");receipt=receipts[eid]
        count=counts.get(eid,0)+1;require(count<=100,"attempt count exceeds 100")
        require(row["data"].get("source_id") in sources,"attempt source missing")
        attempt_source=sources[row["data"]["source_id"]]
        original=sources[receipt["source_id"]]
        require(all(attempt_source["data"][key]==original["data"][key] for key in ("account_id","livemode")),"replacement read source scope differs")
        data=attempt_data(row,app_id,receipt,attempt_source,count);counts[eid]=count;latest[eid]=data["status"]
        for effect in data["effects"]:
            bid=effect["balance_id"]
            require(bid not in observed or observed[bid]==effect,"cash effect changed across attempts")
            observed[bid]=effect
    for eid,receipt in receipts.items():
        initial="PENDING" if receipt["data"]["candidate"] else "UNSUPPORTED"
        require(receipt["status"]==latest.get(eid,initial),"latest receipt state differs")
    return observed


def validate_effect_rows(payload,app_id,observed):
    """Require exactly the cash effects justified by retained successful attempts."""
    seen=set()
    for row in payload["effects"]:
        data=hashed(row,{"app_id","object_id","data","hash","created"});effect_data(data);bid=data["balance_id"]
        require(row["app_id"]==app_id and row["object_id"]==bid and bid not in seen,"effect row scope differs")
        require(observed.get(bid)==data,"effect lacks matching successful attempt")
        seen.add(bid)
    require(seen==set(observed),"cash effect omitted from history")


def export_payments(db,app_id):
    """Export only sanitized records; secret references and active authority are excluded."""
    source_keys=sorted(SOURCE_FIELDS)
    sources=[{k:(checked(r) if k=="data" else r[k]) for k in source_keys} for r in db.execute("SELECT * FROM payment_sources WHERE app_id=? ORDER BY created,id",(app_id,))]
    tables={"receipts":"payment_receipts","attempts":"payment_attempts","effects":"payment_effects"}
    result={"sources":sources,"authority":"HISTORY_ONLY_NO_ENDPOINT_KEYS_OR_ROLES"}
    for key,table in tables.items():
        order="event_id,version" if key=="attempts" else "event_id" if key=="receipts" else "object_id"
        result[key]=[dict(r,data=checked(r)) for r in db.execute("SELECT * FROM "+table+" WHERE app_id=? ORDER BY "+order,(app_id,))]
    validate_complete(result,app_id)
    return result


def validate_complete(payload,app_id):
    """Validate all collections and economic joins without trusting outer JSON hashes."""
    sources,receipts=validate_payload(payload,app_id)
    observed=history_effects(payload,app_id,sources,receipts)
    validate_effect_rows(payload,app_id,observed)


def restore_payments(db,app_id,payload):
    """Restore atomic history only; imported sources cannot receive or reconcile events."""
    if payload is None:return
    validate_complete(payload,app_id)
    for row in payload["sources"]:
        db.execute("INSERT INTO payment_sources VALUES(?,?,?,?,?,?,?,?,?,?)",(app_id,row["id"],canonical(row["data"]),row["hash"],row["version"],"IMPORTED_HISTORY",1,"","",row["created"]))
    for row in payload["receipts"]:
        db.execute("INSERT INTO payment_receipts VALUES(?,?,?,?,?,?,?,?)",(app_id,row["event_id"],row["source_id"],canonical(row["data"]),row["hash"],row["status"],1,row["created"]))
    for row in payload["attempts"]:
        db.execute("INSERT INTO payment_attempts VALUES(?,?,?,?,?,?)",(app_id,row["event_id"],row["version"],canonical(row["data"]),row["hash"],row["created"]))
    for row in payload["effects"]:
        db.execute("INSERT INTO payment_effects VALUES(?,?,?,?,?)",(app_id,row["object_id"],canonical(row["data"]),row["hash"],row["created"]))


def receipt_time_hashes(data):
    """Validate chronological signed receipt and fixed digest formats separately."""
    require(type(data["event_created"]) is int and data["event_created"]>0,"event time invalid")
    require(type(data["signature_timestamp"]) is int and data["signature_timestamp"]>0,"signature time invalid")
    received=iso_time(data["received_at"])
    require(abs(received.timestamp()-data["signature_timestamp"])<=301,"signature receipt window differs")
    require(data["event_created"]<=received.timestamp()+300,"event future time differs")
    require(data["verification"]=="SIGNATURE_VERIFIED_CONFIGURED_SECRET","verification label differs")
    for key in ("body_sha256","content_sha256"):
        require(isinstance(data[key],str) and re.fullmatch(r"[a-f0-9]{64}",data[key]),"receipt digest invalid")


def attempt_effects(data,receipt,src):
    """Validate cash-state cardinality and source-bound compensating pairs."""
    effects=data["effects"];require(isinstance(effects,list) and len(effects)<=2,"attempt effects invalid")
    require(bool(effects)==(data["status"] in ("RECONCILED","DUPLICATE_EFFECT")),"attempt cash state differs")
    for effect in effects:bound_effect(effect,receipt,src)
    if len(effects)==2:paired_effects(effects)
