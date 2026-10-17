"""Durable native-verified postbacks, immutable map bindings and visible redacted recovery."""
import hashlib
from .common import Invalid,canonical,digest,now,uid
from .db import connection
from .review_access import member
from .store import audit
from .attribution_sources import Sources,source,checked,current_authority
from .attribution_maps import Maps,mapping
from . import attribution_skan,attribution_aak
from .attribution_reporting import report


def room(db,app):
    """Enforce one shared bounded attribution observation/request history."""
    receipts=db.execute("SELECT COUNT(*) FROM attribution_receipts WHERE app_id=?",(app,)).fetchone()[0]
    reads=db.execute("SELECT COUNT(*) FROM attribution_reads WHERE app_id=?",(app,)).fetchone()[0]
    if receipts+reads>=10000:raise Invalid("Attribution history reached 10000 observations/reads")


def failure(store,app,sid,body_hash,code="VERIFICATION_FAILED"):
    """Retain only a finite failure code, digest and repair action, never raw input."""
    data={"body_sha256":body_hash,"code":code,"retry":"RESELECT_FRESH_INPUT"}
    with connection(store.path) as db:
        db.execute("INSERT INTO attribution_failures VALUES(?,?,?,?,?,?,?)",(app,uid(),sid,canonical(data),digest(data),0,now()))
        db.execute("DELETE FROM attribution_failures WHERE app_id=? AND id NOT IN (SELECT id FROM attribution_failures WHERE app_id=? ORDER BY rowid DESC LIMIT 1000)",(app,app))
        audit(db,app,"attribution.input_failed",{"source_id":sid,"code":code,"body_sha256":body_hash})


def receipt(row):
    """Reject inconsistent signed identity or stored content hashes."""
    value=checked(row)
    if value["identity"]!=value["data"]["observation"]["identity"]:raise Invalid("Attribution receipt identity differs")
    return value


def commit(db,app,current,selected,observation,body_hash,verification):
    """Preserve duplicates and unsigned conflicts as immutable evidence."""
    identity=observation["identity"];claim=observation.get("signed_sha256",digest(observation))
    old=[receipt(r) for r in db.execute("SELECT * FROM attribution_receipts WHERE app_id=? AND identity=?",(app,identity))]
    if any(r["data"]["claim_sha256"]!=claim for r in old):raise Invalid("Signed attribution identity conflicts with an earlier receipt")
    if any(r["imported"] for r in old):raise Invalid("Imported identity cannot be promoted to current authority")
    oid=digest({"identity":identity,"unsigned":observation.get("unsigned")})
    same=next((r for r in old if r["id"]==oid),None)
    if same:return {"status":"DUPLICATE","duplicate":True,"id":oid,"hash":same["hash"]}
    room(db,app)
    data={"observation":observation,"claim_sha256":claim,"body_sha256":body_hash,
          "source_hash":current["hash"],"source_version":current["version"],
          "map_hash":selected["hash"] if selected else None,"received_at":now(),"verification":verification}
    db.execute("INSERT INTO attribution_receipts VALUES(?,?,?,?,?,?,?,?,?,?)",
               (app,oid,current["id"],selected["id"] if selected else None,selected["version"] if selected else None,
                identity,canonical(data),digest(data),0,now()))
    status="UNSIGNED_CONFLICT" if old else "VERIFIED" if verification=="NATIVE_APPLE_SIGNATURE" else "API_RETRIEVED"
    audit(db,app,"attribution.observation_saved",{"id":oid,"channel":observation["channel"],"status":status})
    return {"status":status,"duplicate":False,"id":oid,"hash":digest(data)}


class Observations:
    def __init__(self,store):self.store=store

    def list(self,app):
        """Keep real errors, distinct channel reports and passive history visible."""
        self.store.app(app)
        sources=Sources(self.store).list(app);maps=Maps(self.store).list(app)
        with connection(self.store.path) as db:
            rows=[receipt(r) for r in db.execute("SELECT * FROM attribution_receipts WHERE app_id=? ORDER BY created",(app,))]
            failures=[checked(r) for r in db.execute("SELECT * FROM attribution_failures WHERE app_id=? ORDER BY created DESC",(app,))]
            reads=[checked(r) for r in db.execute("SELECT * FROM attribution_reads WHERE app_id=? ORDER BY created DESC",(app,))]
        return {"sources":sources,"maps":maps,"receipts":rows,"failures":failures,"reads":reads,
                "report":report(rows,maps),"public_delivery":"NOT_CONFIGURED_LOOPBACK_ONLY"}

    def ingest(self,app,sid,raw,mid,version,map_hash,user=None):
        """Verify outside SQL locks; current source and role must still match before commit."""
        self.store.app(app)
        with connection(self.store.path) as db:
            original=source(db,app,sid);role=member(db,app,user["principal"],"MAKER") if user else None
            channel=original["data"]["channel"]
            if channel=="AdServices":raise Invalid("Use the explicit AdServices token-read workflow")
            selected=mapping(db,app,mid,version,map_hash,channel)
        body_hash=hashlib.sha256(raw).hexdigest() if isinstance(raw,bytes) and len(raw)<=262144 else None
        try:
            verify=attribution_skan.verified if channel=="SKAdNetwork" else attribution_aak.verified
            observation=verify(raw,int(original["data"]["app_apple_id"]),original["data"]["environment"])
            if observation["sequence"]!=selected["data"]["sequence"]:raise Invalid("Choose this postback's sequence mapping")
        except (Invalid,ValueError,PermissionError):
            failure(self.store,app,sid,body_hash)
            raise Invalid("Attribution verification failed. Check app/environment, original signed file and selected sequence map; reselect the original file to retry.") from None
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current=current_authority(db,app,sid,original,user,role)
            selected=mapping(db,app,mid,version,map_hash,channel)
            return commit(db,app,current,selected,observation,body_hash,"NATIVE_APPLE_SIGNATURE")

    def manual(self,app,sid,user,body):
        """Require explicit file-read consent; preserve exact original JSON text for strict decoding."""
        from .attribution_contract import fields
        fields(body,("raw_json","map_id","map_version","map_hash","confirm_read"))
        if body["confirm_read"] is not True or not isinstance(body["raw_json"],str):
            raise Invalid("Confirm verification of the selected original file")
        return self.ingest(app,sid,body["raw_json"].encode("utf-8"),body["map_id"],body["map_version"],body["map_hash"],user)
