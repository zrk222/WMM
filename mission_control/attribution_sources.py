"""Version-bound app-scoped source declarations, never provider ownership claims."""
import json
import re
from .common import Invalid,canonical,digest,now,uid
from .db import connection
from .review_access import member
from .store import audit
from . import attribution_contract as contract

CHANNELS=("SKAdNetwork","AdAttributionKit","AdServices")
PUBLIC_SOURCE={"app_id","id","data","hash","version","status","imported","created"}


def checked(row):
    """Check immutable data bytes before trusting any saved observation."""
    result=dict(row)
    if isinstance(result["data"],str):result["data"]=json.loads(result["data"])
    if digest(result["data"])!=result["hash"]:raise Invalid("Attribution history hash differs")
    return result


def decimal(value):
    """Preserve provider IDs beyond JavaScript safe integers as canonical decimal text."""
    if type(value) is int:value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r"[1-9][0-9]{0,18}",value):
        raise Invalid("Enter a positive numeric Apple identifier")
    contract.integer(int(value),1,9223372036854775807)
    return value


def declaration(body):
    """Require bounded public app identity and exact source-read consent."""
    contract.fields(body,("channel","environment","app_apple_id","org_id","confirm_read"))
    if body["confirm_read"] is not True:raise Invalid("Confirm reads for this app's attribution source")
    channel=body["channel"]
    if channel not in CHANNELS:raise Invalid("Choose a supported Apple attribution channel")
    org=decimal(body["org_id"]) if channel=="AdServices" else None
    if channel!="AdServices" and body["org_id"] is not None:raise Invalid("Organization is only used for AdServices")
    return {"channel":channel,"environment":contract.environment_name(body["environment"]),
            "app_apple_id":decimal(body["app_apple_id"]),"org_id":org}


def source(db,app,sid,active=True):
    """Resolve only the exact selected app; passive history cannot ingest."""
    row=db.execute("SELECT * FROM attribution_sources WHERE app_id=? AND id=?",(app,sid)).fetchone()
    if not row:raise KeyError("Attribution source not found")
    result=checked(row)
    if active and (result["status"]!="ACTIVE" or result["imported"] or result["read_grant"]!=1):
        raise Invalid("Attribution source is disconnected or historical; set up a current source")
    return result


def capacity(db,app,data):
    """Bound sources and prevent an active provider app scope crossing workspaces."""
    if db.execute("SELECT COUNT(*) FROM attribution_sources WHERE app_id=?",(app,)).fetchone()[0]>=100:
        raise Invalid("Attribution source history reached 100 entries")
    key=digest({k:data[k] for k in ("app_apple_id","channel","environment")})
    rows=db.execute("SELECT app_id,data FROM attribution_sources WHERE status='ACTIVE' AND imported=0").fetchall()
    for row in rows:
        current=json.loads(row["data"])
        if row["app_id"]==app and all(current[k]==data[k] for k in ("channel","environment")):
            raise Invalid("Disconnect the existing channel/environment source first")
        if row["app_id"]!=app and all(current[k]==data[k] for k in ("app_apple_id","channel","environment")):
            raise Invalid("This Apple app/channel/environment is active in another workspace")
    return key


def current_authority(db,app,sid,original,user,role):
    """Recheck source/read grant and role version after verification or transport."""
    current=source(db,app,sid)
    if current["hash"]!=original["hash"] or current["version"]!=original["version"]:
        raise Invalid("Attribution source changed during processing; reload and try a fresh input")
    if user and member(db,app,user["principal"],"MAKER")["version"]!=role["version"]:
        raise Invalid("App role changed during processing")
    return current


class Sources:
    def __init__(self,store):self.store=store

    def list(self,app):
        """Return public source declarations without read grants or credentials."""
        self.store.app(app)
        with connection(self.store.path) as db:
            return [{k:checked(row)[k] for k in PUBLIC_SOURCE} for row in
                    db.execute("SELECT * FROM attribution_sources WHERE app_id=? ORDER BY created DESC",(app,))]

    def create(self,app,user,body):
        """Create one source under the fresh app owner's current local membership."""
        self.store.app(app);data=declaration(body);sid=uid()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app,user["principal"],"OWNER")
            key=capacity(db,app,data)
            db.execute("INSERT INTO attribution_sources VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (app,sid,canonical(data),digest(data),1,"ACTIVE",0,key,1,now()))
            audit(db,app,"attribution.source_declared",{"id":sid,"channel":data["channel"],"scope":"DECLARED_APP_ONLY"})
        return next(row for row in self.list(app) if row["id"]==sid)

    def disconnect(self,app,sid,user,body):
        """Invalidate in-flight work while retaining every historical observation."""
        contract.fields(body,("version","confirm_disconnect"))
        if body["confirm_disconnect"] is not True:raise Invalid("Confirm local attribution disconnect")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app,user["principal"],"OWNER")
            row=source(db,app,sid)
            contract.integer(body["version"],1,1000000)
            if body["version"]!=row["version"]:raise Invalid("Source changed; reload before disconnect")
            db.execute("UPDATE attribution_sources SET status='DISCONNECTED',read_grant=0,version=version+1 WHERE app_id=? AND id=?",(app,sid))
            audit(db,app,"attribution.source_disconnected",{"id":sid,"actor":user["principal"]})
        return {"status":"DISCONNECTED","provider_configuration_changed":False}
