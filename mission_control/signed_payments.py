"""Durable sanitized Stripe intake and explicit actual-cash reconciliation."""
from datetime import datetime, timezone
import json
from .common import Invalid, canonical, digest, now
from .db import connection
from .payment_signature import normalize, object_id, verify
from .payment_sources import Sources, decoded, protected, source
from .payment_transport import read
from .review_access import member
from .store import audit

TERMINAL={"RECONCILED","DUPLICATE_EFFECT","NO_EFFECT"}


def checked(row):
    """Decode any hash-bound payment receipt/attempt/effect before reporting it."""
    value=json.loads(row["data"])
    if digest(value)!=row["hash"]:raise Invalid("Payment history hash differs")
    return value


def integer(value,name,signed=False):
    """Keep cash in bounded integer minor units with no floating point coercion."""
    lower=-10**12 if signed else 0
    if type(value) is not int or not lower<=value<=10**12:raise Invalid("Payment "+name+" is invalid")
    return value


def identity(obj,kind,oid,mode):
    """Validate exact retrieved object and environment, never trust a supplied URL."""
    if obj.get("object")!=kind or obj.get("id")!=oid or (kind=="charge" and obj.get("livemode") is not mode):
        raise Invalid("Stripe object identity or environment differs")


def charge_scope(charge,config,app_id,cid):
    """Require positive captured app-owned charge even when a refund arrives first."""
    identity(charge,"charge",cid,config["livemode"])
    if (charge.get("metadata") or {}).get("growth_app_id")!=app_id:raise Invalid("Charge is not explicitly bound to this app")
    if charge.get("paid") is not True or charge.get("captured") is not True or charge.get("status")!="succeeded":
        raise Invalid("Charge is not a paid captured success")


def candidate(config,receipt,app_id):
    """Fetch at most one refund and its owning charge; preserve absent settlement."""
    kind="charge" if receipt["event_type"]=="charge.succeeded" else "refund"
    obj=read(config,("/charges/" if kind=="charge" else "/refunds/")+receipt["object_id"])
    identity(obj,kind,receipt["object_id"],config["livemode"])
    charge=obj if kind=="charge" else read(config,"/charges/"+receipt["charge_id"])
    charge_scope(charge,config,app_id,receipt["charge_id"])
    if kind=="refund" and obj.get("charge")!=receipt["charge_id"]:raise Invalid("Refund owning charge differs")
    return settled_candidate(config,receipt,obj,kind)


def settled_candidate(config,receipt,obj,kind):
    """Separate pending/refund state from identity and app authorization."""
    if kind=="refund" and obj.get("status") in ("failed","canceled"):
        return failed_refund(config,receipt,obj)
    if kind=="refund" and obj.get("status")!="succeeded":return {"status":"PENDING","effects":[]}
    bid=obj.get("balance_transaction")
    if bid is None:return {"status":"PENDING","effects":[]}
    object_id(bid,"txn")
    balance=read(config,"/balance_transactions/"+bid)
    return cash_result(config,receipt,obj,balance,kind)


def failed_refund(config,receipt,obj):
    """Require both actual debit and compensating credit before failed-refund totals."""
    debit=obj.get("balance_transaction");credit=obj.get("failure_balance_transaction")
    if debit is None and credit is None:return {"status":"NO_EFFECT","effects":[]}
    if not debit or not credit:return {"status":"PENDING","effects":[]}
    object_id(debit,"txn");object_id(credit,"txn")
    first=cash_result(config,receipt,obj,read(config,"/balance_transactions/"+debit),"refund")
    failed=dict(obj,balance_transaction=credit)
    second=cash_result(config,receipt,failed,read(config,"/balance_transactions/"+credit),"refund_reversal")
    for result in (first,second):
        if result["status"]!="RECONCILED":return result
    return {"status":"RECONCILED","effects":first["effects"]+second["effects"]}


def cash_result(config,receipt,obj,balance,kind):
    """Bind actual settlement source, currency and fee arithmetic before any effect."""
    if balance.get("object")!="balance_transaction" or balance.get("id")!=obj["balance_transaction"]:
        raise Invalid("Balance transaction identity differs")
    if balance.get("source")!=obj["id"]:raise Invalid("Balance transaction belongs to another object")
    if balance.get("status")!="available":return {"status":"PENDING","effects":[]}
    cur=settlement_currency(obj)
    if balance.get("currency")!=cur:return {"status":"FX_RECONCILIATION_REQUIRED","effects":[]}
    gross,fee,net=cash_amounts(obj,balance,kind)
    created=settlement_time(balance.get("created"))
    effect={"account_id":config["account_id"],"livemode":config["livemode"],"object_id":obj["id"],"kind":kind,"charge_id":receipt["charge_id"],
            "balance_id":balance["id"],"currency":cur.upper(),"gross_minor":gross,"fee_minor":fee,"net_minor":net,
            "occurred_at":datetime.fromtimestamp(created,timezone.utc).isoformat(),"attribution":"UNALLOCATED"}
    return {"status":"RECONCILED","effects":[effect]}


def append_attempt(db,app_id,eid,data):
    """Append contiguous immutable attempts and publish the latest receipt state."""
    version=db.execute("SELECT COUNT(*) FROM payment_attempts WHERE app_id=? AND event_id=?",(app_id,eid)).fetchone()[0]+1
    if version>100:raise Invalid("Payment receipt reached 100 attempts; inspect history")
    db.execute("INSERT INTO payment_attempts VALUES(?,?,?,?,?,?)",(app_id,eid,version,canonical(data),digest(data),now()))
    db.execute("UPDATE payment_receipts SET status=? WHERE app_id=? AND event_id=?",(data["status"],app_id,eid))
    return version


def effect_once(db,app_id,effects):
    """Validate all economic identities before inserting an atomic debit/credit pair."""
    prior=[]
    for effect in effects:
        old=db.execute("SELECT * FROM payment_effects WHERE app_id=? AND object_id=?",(app_id,effect["balance_id"])).fetchone()
        if old and checked(old)!=effect:
            return {"status":"FAILED","effects":[],"error":"Settlement differs from immutable earlier cash effect; investigate provider adjustment."}
        prior.append(old is not None)
    for effect,exists in zip(effects,prior):
        if not exists:
            db.execute("INSERT INTO payment_effects VALUES(?,?,?,?,?)",(app_id,effect["balance_id"],canonical(effect),digest(effect),now()))
    return {"status":"DUPLICATE_EFFECT" if all(prior) else "RECONCILED","effects":effects}


def cash_report(receipts,effects):
    """Return known net cash, never earned revenue or attributed cohort economics."""
    groups={}
    for effect in effects:
        key=(effect["currency"],effect["livemode"])
        row=groups.setdefault(key,{"currency":key[0],"livemode":key[1],"gross_inflow_minor":0,"refund_outflow_minor":0,"refund_reversal_inflow_minor":0,"fees_minor":0,"net_cash_minor":0})
        row["gross_inflow_minor"]+=effect["gross_minor"] if effect["kind"]=="charge" else 0
        row["refund_reversal_inflow_minor"]+=effect["gross_minor"] if effect["kind"]=="refund_reversal" else 0
        row["refund_outflow_minor"]+=max(0,-effect["gross_minor"])
        row["fees_minor"]+=effect["fee_minor"];row["net_cash_minor"]+=effect["net_minor"]
    incomplete=sum(r["status"] not in TERMINAL or r["imported"] for r in receipts)
    return {"status":"INCOMPLETE" if incomplete else "NO_DATA" if not receipts else "COMPLETE_CONFIGURED_SOURCE",
            "unresolved_receipts":incomplete,"known_subtotals":list(groups.values()),
            "complete_totals":None if incomplete or not receipts else list(groups.values()),
            "coverage":"DELIVERED_RECORDS_ONLY_NOT_ACCOUNT_TOTALS","meaning":"NET_CASH_NOT_EARNED_REVENUE","attribution":"UNALLOCATED","provider_authenticity":"CONFIGURED_SHARED_SECRET_AND_READ_KEY"}


class Payments:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Read sanitized immutable records and explicit reconciliation gaps."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            receipts=[dict(r,data=checked(r)) for r in db.execute("SELECT * FROM payment_receipts WHERE app_id=? ORDER BY created DESC",(app_id,))]
            attempts=[dict(r,data=checked(r)) for r in db.execute("SELECT * FROM payment_attempts WHERE app_id=? ORDER BY event_id,version",(app_id,))]
            effects=[checked(r) for r in db.execute("SELECT * FROM payment_effects WHERE app_id=? ORDER BY object_id",(app_id,))]
        return {"sources":Sources(self.store).list(app_id),"receipts":receipts,"attempts":attempts,"effects":effects,"cash":cash_report(receipts,effects)}

    def intake(self,app_id,source_id,raw,header):
        """Verify first, commit sanitized receipt atomically, and perform no network call."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");row=source(db,app_id,source_id);config=protected(self.store,app_id,row)
            stamp=verify(raw,header,config["endpoint_secret"]);data=normalize(raw,config,app_id)
            data.update(source_hash=row["hash"],source_version=row["version"],signature_timestamp=stamp,
                        verification="SIGNATURE_VERIFIED_CONFIGURED_SECRET",received_at=now())
            old=db.execute("SELECT * FROM payment_receipts WHERE app_id=? AND event_id=?",(app_id,data["event_id"])).fetchone()
            if old:return self.duplicate(old,data)
            if db.execute("SELECT COUNT(*) FROM payment_receipts WHERE app_id=?",(app_id,)).fetchone()[0]>=10000:raise Invalid("Payment receipt capacity is 10000 per app")
            status="PENDING" if data["candidate"] else "UNSUPPORTED"
            db.execute("INSERT INTO payment_receipts VALUES(?,?,?,?,?,?,?,?)",(app_id,data["event_id"],source_id,canonical(data),digest(data),status,0,now()))
            audit(db,app_id,"payment.signed_received",{"source_id":source_id,"event_id":data["event_id"],"status":status})
        return {"event_id":data["event_id"],"status":status,"duplicate":False}

    def duplicate(self,old,data):
        """Allow equivalent JSON resend; never accept identity collision or double count."""
        previous=checked(old)
        if previous["content_sha256"]!=data["content_sha256"]:raise Invalid("Payment event ID conflicts with earlier content")
        return {"event_id":data["event_id"],"status":old["status"],"duplicate":True}

    def reconcile(self,app_id,event_id,user,body):
        """Perform only explicit current-source reads; commit attempts under fresh role version."""
        if set(body)!={"receipt_hash","confirm_read","source_id"} or body["confirm_read"] is not True:raise Invalid("Confirm exact receipt read-only reconciliation")
        self.store.app(app_id)
        with connection(self.store.path) as db:
            role,receipt,data,row=prepare_read(db,app_id,event_id,user,body)
            config=protected(self.store,app_id,row)
        try:result=candidate(config,data,app_id)
        except (Invalid,ValueError,TypeError,KeyError):
            result={"status":"FAILED","effects":[],"error":"Stripe object, scope or settlement read failed. Inspect configuration and retry; no cash effect was guessed."}
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current_read(db,app_id,user,row,role)
            if result["effects"]:result=effect_once(db,app_id,result["effects"])
            attempt=dict(result,receipt_hash=receipt["hash"],source_id=row["id"],source_version=row["version"],
                         actor=user["principal"],role_version=role["version"],read_at=now(),authority="READ_ONLY_CONFIGURED_KEY")
            version=append_attempt(db,app_id,event_id,attempt)
            audit(db,app_id,"payment.reconciled",{"event_id":event_id,"version":version,"status":result["status"]})
        return dict(attempt,version=version)


def settlement_currency(obj):
    """Require explicit non-guessed three-letter source currency."""
    cur=obj.get("currency")
    if not isinstance(cur,str) or len(cur)!=3 or not cur.isascii() or not cur.islower() or not cur.isalpha():
        raise Invalid("Payment currency is invalid")
    return cur


def cash_amounts(obj,balance,kind):
    """Require exact signed minor-unit gross/fee/net arithmetic."""
    amount=integer(obj.get("amount_captured") if kind=="charge" else obj.get("amount"),"gross")
    gross=-amount if kind=="refund" else amount
    fee=integer(balance.get("fee"),"fee",True);net=integer(balance.get("net"),"net",True)
    if amount<=0 or balance.get("amount")!=gross or type(balance.get("amount")) is not int or net!=gross-fee:
        raise Invalid("Actual balance gross/fee/net does not reconcile")
    return gross,fee,net


def settlement_time(value):
    """Validate settlement epoch before constructing a UTC datetime."""
    created=integer(value,"settlement time")
    if not 0<created<=datetime.now(timezone.utc).timestamp()+300:raise Invalid("Balance transaction date is invalid")
    return created


def prepare_read(db,app_id,event_id,user,body):
    """Resolve current receipt, matching active read source and current role together."""
    role=member(db,app_id,user["principal"],"MAKER")
    receipt=db.execute("SELECT * FROM payment_receipts WHERE app_id=? AND event_id=?",(app_id,event_id)).fetchone()
    if not receipt:raise KeyError("Payment receipt not found")
    if body["receipt_hash"]!=receipt["hash"] or receipt["imported"]:raise Invalid("Payment receipt changed or is imported history only")
    data=checked(receipt);original=source(db,app_id,receipt["source_id"],False)
    row=source(db,app_id,body["source_id"])
    if any(row["data"][key]!=original["data"][key] for key in ("account_id","livemode")):
        raise Invalid("Replacement read source belongs to another account or environment")
    if not data["candidate"]:raise Invalid("This event type has no supported cash reconciliation")
    return role,receipt,data,row


def current_read(db,app_id,user,row,role):
    """Recheck current active authority after external reads and before cash commit."""
    current=member(db,app_id,user["principal"],"MAKER")
    current_source=source(db,app_id,row["id"])
    if current["version"]!=role["version"] or current_source["version"]!=row["version"]:
        raise Invalid("Payment source or role changed during read; retry after review")
