"""Durable signed StoreKit intake with immutable sanitized records and visible retry failures."""
import hashlib
import json
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .review_access import member
from .store import audit
from .payment_signature import strict_json
from .storekit_contract import normalize
from .storekit_sources import Sources, source, checked
from .storekit_lifecycle import report


def receipt(row):
    """Require current stored receipt hash and matching notification identity."""
    result=checked(row)
    if result["id"]!=result["data"]["notification"]["notification_id"]:
        raise Invalid("StoreKit stored notification identity differs")
    return result


def intake_body(raw):
    """Only signedPayload is accepted from a bounded exact JSON object."""
    body=strict_json(raw)
    if set(body)!={"signedPayload"} or not isinstance(body["signedPayload"],str):
        raise Invalid("Use the original StoreKit JSON containing only signedPayload")
    return body["signedPayload"]


def current_authority(db,app,sid,original,user,role):
    """Recheck source consent/version and role after native verification finishes."""
    current=source(db,app,sid)
    if current["version"]!=original["version"] or current["hash"]!=original["hash"] or current["read_grant"]!=1:
        raise Invalid("StoreKit source changed during verification; reselect the file after reload")
    if user:
        current_role=member(db,app,user["principal"],"MAKER")
        if current_role["version"]!=role["version"]:raise Invalid("App role changed during verification")
    return current


class Notifications:
    def __init__(self,store):self.store=store

    def list(self,app):
        """Read only this app's public source, verified receipts and redacted failures."""
        self.store.app(app)
        with connection(self.store.path) as db:
            rows=[receipt(r) for r in db.execute("SELECT * FROM storekit_receipts WHERE app_id=? ORDER BY created DESC",(app,))]
            failures=[checked(r) for r in db.execute("SELECT * FROM storekit_failures WHERE app_id=? ORDER BY created DESC",(app,))]
        return {"sources":Sources(self.store).list(app),"receipts":rows,"failures":failures,"report":report(rows),
                "scope":"Native verified notifications; imported history cannot establish current signing authority",
                "public_delivery":"NOT_CONFIGURED_LOOPBACK_ONLY"}

    def ingest(self,app,sid,raw,user=None):
        """Authenticate without a DB lock, then recheck source and role before commit."""
        self.store.app(app)
        with connection(self.store.path) as db:
            original=source(db,app,sid)
            role=member(db,app,user["principal"],"MAKER") if user else None
        if original["read_grant"]!=1:raise Invalid("StoreKit source has no certificate-read grant")
        if not isinstance(raw,bytes) or not 0<len(raw)<=262144:
            self.failure(app,sid,None)
            raise Invalid("StoreKit body must contain 1 through 262144 bytes")
        body_hash=hashlib.sha256(raw).hexdigest()
        try:
            compact=intake_body(raw)
            notification=normalize(compact,original["data"])
        except (Invalid,PermissionError,ValueError):
            self.failure(app,sid,body_hash)
            raise Invalid("StoreKit verification failed. Check app/source, original signed file, system clock and certificate network access, then reselect the file to retry.") from None
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current=current_authority(db,app,sid,original,user,role)
            return self.commit(db,app,current,notification,body_hash)

    def commit(self,db,app,current,notification,body_hash):
        """Idempotently retain one immutable sanitized notification, never raw signed claims."""
        nid=notification["notification_id"]
        old=db.execute("SELECT * FROM storekit_receipts WHERE app_id=? AND id=?",(app,nid)).fetchone()
        content_hash=digest(notification)
        if old:
            existing=receipt(old)
            if existing["data"]["content_sha256"]!=content_hash:
                raise Invalid("StoreKit notification UUID conflicts with an earlier immutable receipt")
            if existing["imported"]:raise Invalid("Imported UUID cannot be promoted to current verification; retain history separately")
            return {"status":"DUPLICATE","duplicate":True,"id":nid,"hash":existing["hash"]}
        if db.execute("SELECT COUNT(*) FROM storekit_receipts WHERE app_id=?",(app,)).fetchone()[0]>=10000:
            raise Invalid("StoreKit notification history reached 10000 entries")
        data={"notification":notification,"content_sha256":content_hash,"body_sha256":body_hash,
              "source_hash":current["hash"],"source_version":current["version"],"verified_at":now(),
              "verification":"NATIVE_APPLE_CHAIN_ES256_AND_REVOCATION"}
        db.execute("INSERT INTO storekit_receipts VALUES(?,?,?,?,?,?,?,?)",(app,nid,current["id"],canonical(data),digest(data),"VERIFIED",0,now()))
        audit(db,app,"storekit.notification_verified",{"id":nid,"type":notification["notification_type"],"body_sha256":body_hash})
        return {"status":"VERIFIED","duplicate":False,"id":nid,"hash":digest(data)}

    def failure(self,app,sid,body_hash):
        """Redacted failures stay visible, without claiming any unverified field or body."""
        data={"body_sha256":body_hash,"code":"VERIFICATION_FAILED","retry":"RESELECT_ORIGINAL_FILE"}
        with connection(self.store.path) as db:
            db.execute("INSERT INTO storekit_failures VALUES(?,?,?,?,?,?,?)",(app,uid(),sid,canonical(data),digest(data),0,now()))
            db.execute("DELETE FROM storekit_failures WHERE app_id=? AND id NOT IN (SELECT id FROM storekit_failures WHERE app_id=? ORDER BY rowid DESC LIMIT 1000)",(app,app))
            audit(db,app,"storekit.verification_failed",{"source_id":sid,"body_sha256":body_hash,"code":"VERIFICATION_FAILED"})

    def manual(self,app,sid,user,body):
        """Fresh authorized UI intake makes its certificate-read effect explicit."""
        if set(body)!={"signedPayload","confirm_read"} or body["confirm_read"] is not True:
            raise Invalid("Confirm online signature checks for this original signed notification")
        raw=canonical({"signedPayload":body["signedPayload"]}).encode()
        return self.ingest(app,sid,raw,user)
