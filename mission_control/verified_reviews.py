"""Exact-source review records with authenticated, distinct maker and checker."""
from datetime import datetime,timedelta,timezone
import json
from .common import Invalid,canonical,digest,iso_time,now,uid
from .db import connection
from .store import audit
from .review_access import member,exact_role


def source(db,app_id,record_id):
    """Freeze current app and eligible record inside the same write transaction."""
    app=db.execute("SELECT * FROM apps WHERE id=?",(app_id,)).fetchone()
    record=db.execute("SELECT * FROM records WHERE app_id=? AND id=?",(app_id,record_id)).fetchone()
    if not app or not record or record["kind"] not in ("distribution","store","experiment"):raise Invalid("Choose this app's distribution, store or experiment record")
    item=dict(record);item["data"]=json.loads(item["data"])
    return app["version"],item


def current(db,row):
    """Recheck exact bytes, app version, active role versions and expiry."""
    packet=json.loads(row["packet"])
    if digest(packet)!=row["hash"]:raise Invalid("Verified packet hash changed")
    if iso_time(row["expires"])<=datetime.now(timezone.utc):raise Invalid("Verified review expired; prepare a fresh packet")
    version,record=source(db,row["app_id"],packet["record"]["id"])
    if version!=packet["manifest_version"] or record!=packet["record"]:raise Invalid("App or source changed; prepare a fresh review")
    exact_role(db,row["app_id"],row["preparer"],packet["maker_role_version"],"MAKER")
    if row["checker"]:exact_role(db,row["app_id"],row["checker"],row["checker_role_version"],"CHECKER")
    return packet


class Reviews:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Keep original history while deriving honest current approval availability."""
        self.store.app(app_id)
        result=[]
        with connection(self.store.path) as db:
            for row in db.execute("SELECT * FROM verified_reviews WHERE app_id=? ORDER BY created DESC LIMIT 100",(app_id,)):
                item=dict(row);item["packet"]=json.loads(item["packet"])
                try:current(db,row);item["availability"]="CURRENT";item["unavailable_reason"]=None
                except (Invalid,PermissionError,KeyError,ValueError) as exc:item["availability"]="UNAVAILABLE";item["unavailable_reason"]=str(exc)
                result.append(item)
        return result

    def prepare(self,app_id,user,body):
        """Freeze exact evidence and authenticated maker role; no execution authority."""
        self.store.app(app_id)
        if set(body)!={"record_id"} or not isinstance(body["record_id"],str):raise Invalid("Choose one source record for verified review")
        review_id=uid();expires=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");role=member(db,app_id,user["principal"],"MAKER")
            version,record=source(db,app_id,body["record_id"])
            packet={"app_id":app_id,"manifest_version":version,"record":record,"maker_role_version":role["version"],
                    "preparer":user["principal"],"authorized_spend_minor":0,"external_execution":"NOT_IMPLEMENTED"}
            db.execute("INSERT INTO verified_reviews(id,app_id,packet,hash,preparer,status,expires,created) VALUES(?,?,?,?,?,?,?,?)",
                       (review_id,app_id,canonical(packet),digest(packet),user["principal"],"WAITING_REVIEW",expires,now()))
            audit(db,app_id,"review.verified_prepared",{"review_id":review_id,"hash":digest(packet),"principal":user["principal"]})
        return next(r for r in self.list(app_id) if r["id"]==review_id)

    def approve(self,app_id,review_id,user,body):
        """Record distinct current checker after atomic source and role validation."""
        self.store.app(app_id)
        if set(body)!={"hash"}:raise Invalid("Submit only the exact inspected packet hash")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM verified_reviews WHERE app_id=? AND id=?",(app_id,review_id)).fetchone()
            if not row or row["status"]!="WAITING_REVIEW":raise Invalid("Verified review is unavailable or already recorded")
            role=member(db,app_id,user["principal"],"CHECKER")
            if row["preparer"]==user["principal"]:raise Invalid("The authenticated maker cannot review their own packet")
            if row["hash"]!=body["hash"]:raise Invalid("The inspected packet hash does not match")
            current(db,row)
            db.execute("UPDATE verified_reviews SET checker=?,checker_role_version=?,status='VERIFIED_REVIEW_RECORDED',reviewed_at=? WHERE id=? AND app_id=?",
                       (user["principal"],role["version"],now(),review_id,app_id))
            audit(db,app_id,"review.verified_recorded",{"review_id":review_id,"hash":row["hash"],"principal":user["principal"]})
        return next(r for r in self.list(app_id) if r["id"]==review_id)
