"""App-owned protected Stripe source setup with exact role and disconnect boundaries."""
import hashlib
import json
import re
import uuid
from .common import Invalid, canonical, digest, identifier, now
from .credential_vault import Vault, namespace
from .db import connection
from .payment_transport import read
from .review_access import member
from .store import audit


def credential_name(store,app_id,reference):
    """Create only an app/database/UUID-scoped native target, never a supplied name."""
    identifier(app_id)
    if not re.fullmatch(r"[a-f0-9-]{36}",reference):raise Invalid("Payment credential reference is invalid")
    return "AppGrowthPayments/"+namespace(store.path)+"/"+app_id+"/"+reference


def decoded(row):
    """Reject modified source metadata before an endpoint or credential is resolved."""
    result=dict(row);result["data"]=json.loads(row["data"])
    if digest(result["data"])!=row["hash"]:raise Invalid("Payment source history hash differs")
    return result


def source(db,app_id,source_id,active=True):
    """Resolve the exact app-owned, nonimported active source."""
    row=db.execute("SELECT * FROM payment_sources WHERE app_id=? AND id=?",(app_id,source_id)).fetchone()
    if not row:raise KeyError("Payment source not found")
    result=decoded(row)
    if active and (result["status"]!="ACTIVE" or result["imported"]):raise Invalid("Payment source is disconnected or imported history only")
    return result


def protected(store,app_id,row):
    """Read exact native credentials and validate their local source binding."""
    value=Vault().get(credential_name(store,app_id,row["credential_ref"]))
    if not value:raise Invalid("Payment credential is missing; disconnect and reconnect this source")
    if value.get("binding")!={"app_id":app_id,"source_id":row["id"],"hash":row["hash"]}:
        raise Invalid("Payment credential binding differs; reconnect this source")
    return dict(row["data"],api_key=value["api_key"],endpoint_secret=value["endpoint_secret"])


def declaration(body):
    """Validate finite configuration, mode-specific keys and explicit read consent."""
    fields={"account_id","livemode","api_version","api_key","endpoint_secret","confirm_read"}
    if not isinstance(body,dict) or set(body)!=fields or body["confirm_read"] is not True:
        raise Invalid("Confirm the read-only Stripe account check and provide all setup fields")
    if not re.fullmatch(r"acct_[A-Za-z0-9]{1,110}",str(body["account_id"])):raise Invalid("Stripe account ID is invalid")
    if type(body["livemode"]) is not bool:raise Invalid("Choose test or live mode")
    if not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}(?:[.][a-z]+)?",str(body["api_version"])):raise Invalid("Use the exact snapshot API version from Stripe")
    mode="live" if body["livemode"] else "test"
    if not re.fullmatch(r"rk_"+mode+r"_[A-Za-z0-9]{16,200}",str(body["api_key"])):raise Invalid("Use a read-only restricted key matching the selected mode")
    if not re.fullmatch(r"whsec_[A-Za-z0-9]{16,200}",str(body["endpoint_secret"])):raise Invalid("Use the endpoint-specific whsec signing secret")
    return {key:body[key] for key in ("account_id","livemode","api_version")}


def capacity(db,app_id,fingerprint):
    """Enforce bounded identities and prevent the same secret serving different apps."""
    if db.execute("SELECT COUNT(*) FROM payment_sources WHERE app_id=?",(app_id,)).fetchone()[0]>=100:raise Invalid("Payment source history reached 100 entries")
    if db.execute("SELECT 1 FROM payment_sources WHERE app_id=? AND status='ACTIVE'",(app_id,)).fetchone():raise Invalid("Disconnect the current source before replacement")
    if db.execute("SELECT 1 FROM payment_sources WHERE app_id<>? AND secret_hash=?",(app_id,fingerprint)).fetchone():raise Invalid("Use a separate endpoint signing secret for each app")


class Sources:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Expose sanitized source status; credentials and fingerprints never leave service."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[decoded(r) for r in db.execute("SELECT * FROM payment_sources WHERE app_id=? ORDER BY created DESC",(app_id,))]
        return [{k:r[k] for k in ("id","data","hash","version","status","imported","created")} for r in rows]

    def create(self,app_id,user,body):
        """Check actual account read access, protect keys and commit under current owner."""
        self.store.app(app_id);data=declaration(body);fingerprint=hashlib.sha256(body["endpoint_secret"].encode()).hexdigest()
        with connection(self.store.path) as db:
            role=member(db,app_id,user["principal"],"OWNER");capacity(db,app_id,fingerprint)
        config=dict(data,api_key=body["api_key"])
        account=read(config,"/account")
        if account.get("object")!="account" or account.get("id")!=data["account_id"]:raise Invalid("Read key belongs to another Stripe account")
        sid=str(uuid.uuid4());ref=str(uuid.uuid4());sha=digest(data);name=credential_name(self.store,app_id,ref)
        value={"binding":{"app_id":app_id,"source_id":sid,"hash":sha},"api_key":body["api_key"],"endpoint_secret":body["endpoint_secret"]}
        Vault().put(name,value)
        try:
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                current=member(db,app_id,user["principal"],"OWNER")
                if current["version"]!=role["version"]:raise Invalid("Owner role changed during setup; retry with fresh identity")
                capacity(db,app_id,fingerprint)
                db.execute("INSERT INTO payment_sources VALUES(?,?,?,?,?,?,?,?,?,?)",(app_id,sid,canonical(data),sha,1,"ACTIVE",0,ref,fingerprint,now()))
                audit(db,app_id,"payment.source_configured",{"id":sid,"account_id":data["account_id"],"livemode":data["livemode"],"actor":user["principal"]})
        except Exception:
            Vault().delete(name)
            raise
        return next(r for r in self.list(app_id) if r["id"]==sid)

    def disconnect(self,app_id,source_id,user,body):
        """Disable intake before key deletion; a failed deletion remains retryable."""
        if set(body)!={"version","confirm_disconnect"} or body["confirm_disconnect"] is not True:raise Invalid("Confirm disconnect with the exact source version")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app_id,user["principal"],"OWNER")
            row=source(db,app_id,source_id,False)
            if row["imported"]:raise Invalid("Imported history has no local credential")
            if type(body["version"]) is not int or body["version"]!=row["version"]:raise Invalid("Payment source changed; reload before disconnect")
            db.execute("UPDATE payment_sources SET status='CLEANUP_REQUIRED',version=version+1 WHERE app_id=? AND id=?",(app_id,source_id))
            audit(db,app_id,"payment.source_disabled",{"id":source_id,"actor":user["principal"]})
        try:Vault().delete(credential_name(self.store,app_id,row["credential_ref"]))
        except Invalid:return {"status":"CLEANUP_REQUIRED","message":"Intake is disabled. Retry disconnect to remove the local protected credential."}
        with connection(self.store.path) as db:
            db.execute("UPDATE payment_sources SET status='DISCONNECTED' WHERE app_id=? AND id=?",(app_id,source_id))
        return {"status":"DISCONNECTED"}
