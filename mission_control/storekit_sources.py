"""Fresh-owner StoreKit source declaration; never claims Apple account ownership."""
import json
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .review_access import member
from .store import audit
from .storekit_contract import declaration


def checked(row):
    """Verify stored JSON integrity before using an app/source binding."""
    result=dict(row);result["data"]=json.loads(row["data"])
    if digest(result["data"])!=row["hash"]:raise Invalid("StoreKit history hash differs")
    return result


def source(db,app,sid,active=True):
    """Resolve a source only within its exact app; historical snapshots cannot ingest."""
    row=db.execute("SELECT * FROM storekit_sources WHERE app_id=? AND id=?",(app,sid)).fetchone()
    if not row:raise KeyError("StoreKit source not found")
    result=checked(row)
    if active and (result["status"]!="ACTIVE" or result["imported"]):
        raise Invalid("StoreKit source is disconnected or imported history")
    return result


def capacity(db,app,data):
    """Enforce finite history and prevent an active bundle/environment crossing apps."""
    if db.execute("SELECT COUNT(*) FROM storekit_sources WHERE app_id=?",(app,)).fetchone()[0]>=100:
        raise Invalid("StoreKit source history reached 100 entries")
    if db.execute("SELECT 1 FROM storekit_sources WHERE app_id=? AND status='ACTIVE'",(app,)).fetchone():
        raise Invalid("Disconnect the current StoreKit source before replacing it")
    key=digest({"bundle_id":data["bundle_id"],"environment":data["environment"]})
    if db.execute("SELECT 1 FROM storekit_sources WHERE app_id<>? AND scope_key=? AND status='ACTIVE'",(app,key)).fetchone():
        raise Invalid("This app bundle/environment is already bound to another workspace")
    return key


class Sources:
    def __init__(self,store):self.store=store

    def list(self,app):
        """Return public declaration metadata; no provider credential exists here."""
        self.store.app(app)
        with connection(self.store.path) as db:
            rows=[checked(r) for r in db.execute("SELECT * FROM storekit_sources WHERE app_id=? ORDER BY created DESC",(app,))]
        return [{key:r[key] for key in ("id","data","hash","version","status","imported","created")} for r in rows]

    def create(self,app,user,body):
        """Record the current owner's explicit consent; no Apple account ownership inference."""
        self.store.app(app);data=declaration(body);sid=uid()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app,user["principal"],"OWNER")
            key=capacity(db,app,data)
            db.execute("INSERT INTO storekit_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (app,sid,canonical(data),digest(data),1,"ACTIVE",0,key,1,now()))
            audit(db,app,"storekit.source_declared",{"id":sid,"actor":user["principal"],"identity":"DECLARED_APP_ONLY"})
        return next(row for row in self.list(app) if row["id"]==sid)

    def disconnect(self,app,sid,user,body):
        """Invalidate in-flight verification and future intake without deleting history."""
        if set(body)!={"version","confirm_disconnect"} or body["confirm_disconnect"] is not True:
            raise Invalid("Confirm local StoreKit disconnect")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app,user["principal"],"OWNER")
            row=source(db,app,sid,False)
            if row["imported"]:raise Invalid("Imported history has no active local source")
            if type(body["version"]) is not int or row["version"]!=body["version"]:
                raise Invalid("StoreKit source changed; reload before disconnect")
            db.execute("UPDATE storekit_sources SET status='DISCONNECTED',read_grant=0,version=version+1 WHERE app_id=? AND id=?",(app,sid))
            audit(db,app,"storekit.source_disconnected",{"id":sid,"actor":user["principal"]})
        return {"status":"DISCONNECTED","provider_configuration_changed":False}
