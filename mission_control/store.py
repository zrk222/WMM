"""App-scoped data access, version conflicts and portable snapshot validation."""
import json
import base64
import hashlib
import re
from pathlib import Path
from .common import Invalid, canonical, digest, identifier, now, required, safe_data, uid
from .db import connection, initialize
from .catalog import FIELDS
from .ledger import Ledger, restore_ledger, validate_snapshot
from .experiments import Experiments, restore_experiments, snapshot_data
from .experiment_schedules import export_schedules,restore_schedules
from .creative_library import export_library,restore_library
from .creative_portable import export_production,restore_production
from .production_portable import export_capabilities,restore_capabilities
from .creative_rank_portable import export_rankings,restore_rankings
from .acquisition_portable import export_acquisition,restore_acquisition
from .media_portable import export_media,restore_media
from .automation_policy import validate_manifest, check_manifest_version


def decode(row):
    """Decode structured SQLite fields without changing scalar metadata."""
    result = dict(row)
    for key in ("data", "result", "packet", "detail"):
        if result.get(key):
            result[key] = json.loads(result[key])
    return result


def audit(db, app_id, action, detail):
    """Append an app-scoped immutable description of a completed local change."""
    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)", (app_id,action,canonical(detail),now()))


def app_data(data):
    """Normalize manifest fields and preserve zero automatic spending authority."""
    safe_data(data)
    validate_manifest(data)
    result = dict(data)
    from .play_contract import manifest_target
    result.update(manifest_target(result))
    result["name"] = required(data.get("name"), "App name", 100)
    for field in ("job", "audience", "activation", "release", "locale", "currency"):
        result[field] = str(data.get(field) or "").strip()
    for field in ("brand_voice","brand_visual","brand_source","brand_boundaries"):
        if field in data:
            value=data[field]
            if not isinstance(value,str) or len(value)>2000:raise Invalid(field+": use text up to 2000 characters")
            result[field]=value.strip()
    result["authorized_spend_minor"] = 0
    if result.get("website"):
        from .aeo_transport import public_url
        result["website"] = public_url(result["website"])
    if 'social_callback_base_url' in result:
        from .social_contract import relay_base
        result['social_callback_base_url']=relay_base(result['social_callback_base_url'])
    return result


class Store:
    def __init__(self, path, seed=True):
        self.path = Path(path)
        initialize(self.path)
        if seed:
            self.seed()

    def seed(self):
        """Add unknown seed app manifests without replacing existing workspaces."""
        source = Path(__file__).resolve().parents[1]/"package/app-profiles.json"
        profiles = json.loads(source.read_text(encoding="utf-8-sig"))["apps"]
        with connection(self.path) as db:
            for profile in profiles:
                data = app_data(dict(profile, job=profile["audience_hypothesis"], audience=profile["audience_hypothesis"]))
                db.execute("INSERT OR IGNORE INTO apps(id,data,updated) VALUES(?,?,?)", (profile["app_id"],canonical(data),now()))

    def apps(self):
        """List stored workspaces without combining their user or evidence data."""
        with connection(self.path) as db:
            return [decode(r) for r in db.execute("SELECT * FROM apps ORDER BY rowid")]

    def app(self, app_id):
        """Resolve an exact app namespace or return an explicit missing-workspace error."""
        with connection(self.path) as db:
            row = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
        if row is None:
            raise KeyError("App workspace not found")
        return decode(row)

    def save_app(self, app_id, data, version=None):
        """Create or version-check a manifest before committing an audited update."""
        app_id = identifier(app_id)
        data = app_data(data)
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
            if row and row["version"] != version:
                raise Invalid("Workspace changed. Reload before saving.")
            if row:
                db.execute("UPDATE apps SET data=?,version=version+1,updated=? WHERE id=?",(canonical(data),now(),app_id))
            else:
                db.execute("INSERT INTO apps(id,data,updated) VALUES(?,?,?)",(app_id,canonical(data),now()))
            audit(db,app_id,"workspace.saved",{"version": (row["version"]+1) if row else 1})
        return self.app(app_id)

    def records(self, app_id):
        """Read evidence for one existing workspace, ordered by freshness."""
        self.app(app_id)
        with connection(self.path) as db:
            return [decode(r) for r in db.execute("SELECT * FROM records WHERE app_id=? ORDER BY updated DESC,id",(app_id,))]

    def save_record(self, app_id, body, provenance="operator"):
        """Persist source-bound evidence with scope and optimistic version checks."""
        self.app(app_id)
        kind = body.get("kind")
        if kind not in FIELDS:
            raise Invalid("Choose a known evidence type")
        title = required(body.get("title"),"Evidence title",200)
        source = required(body.get("source"),"Source reference",2000)
        safe_data({"source_reference":source})
        data = safe_data(body.get("data"))
        record_id = body.get("id") or uid()
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check_manifest_version(db, app_id, body.get("manifest_version"))
            self._write_record(db,app_id,record_id,kind,title,source,data,provenance,body.get("version"))
        return next(r for r in self.records(app_id) if r["id"]==record_id)

    def _write_record(self, db, app_id, record_id, kind, title, source, data, provenance, version):
        old = db.execute("SELECT * FROM records WHERE id=?",(record_id,)).fetchone()
        if old and (old["app_id"] != app_id or old["version"] != version):
            raise Invalid("Evidence conflict or workspace mismatch. Reload first.")
        value_hash = digest({"kind":kind,"data":data,"source":source})
        if old:
            db.execute("UPDATE records SET kind=?,title=?,source=?,data=?,provenance=?,hash=?,version=version+1,updated=? WHERE id=?",(kind,title,source,canonical(data),provenance,value_hash,now(),record_id))
        else:
            db.execute("INSERT INTO records(id,app_id,kind,title,data,source,provenance,hash,updated) VALUES(?,?,?,?,?,?,?,?,?)",(record_id,app_id,kind,title,canonical(data),source,provenance,value_hash,now()))
        audit(db,app_id,"evidence.saved",{"id":record_id,"hash":value_hash,"previous_hash":old["hash"] if old else None})

    def history(self, app_id):
        """Return the bounded most-recent audit history for one workspace."""
        self.app(app_id)
        with connection(self.path) as db:
            return [decode(r) for r in db.execute("SELECT * FROM audit WHERE app_id=? ORDER BY id DESC LIMIT 100",(app_id,))]

    def export(self, app_id):
        """Build a hash-bound per-app snapshot with its referenced image bytes."""
        payload={"schema":"growth.snapshot.v1","app":self.app(app_id),"records":self.records(app_id)}
        payload["files"]=self._export_files(app_id,payload["records"])
        payload["ledger"]=Ledger(self.path).export(app_id)
        validate_snapshot(payload["ledger"])
        payload["experiments"]=[{k:v for k,v in e.items() if k!="decision_status"} for e in Experiments(self).list(app_id)]
        snapshot_data(payload["experiments"])
        payload["schedules"]=export_schedules(self,app_id)
        payload["references"]=export_library(self,app_id)
        with connection(self.path) as db:
            payload["capabilities"]=export_capabilities(db,app_id)
            payload["production"]=export_production(db,app_id)
        with connection(self.path) as db:payload["rankings"]=export_rankings(db,app_id)
        with connection(self.path) as db:payload["acquisition"]=export_acquisition(db,app_id)
        payload["media"]=export_media(self,app_id)
        payload.update(self._export_observations(app_id))
        snapshot={"payload":payload,"sha256":digest(payload),"exported_at":now()}
        if len(canonical(snapshot).encode())>33554432:raise Invalid("Workspace exceeds the portable snapshot limit. Download rendered videos individually and use a full local workspace backup before migration.")
        return snapshot

    def _export_observations(self,app_id):
        """Keep existing portable sections and independent read transactions in declared order."""
        from .learning_portable import export_learning
        from .payment_portable import export_payments
        from .storekit_portable import export_storekit
        from .attribution_portable import export_attribution
        from .aeo_portable import export_aeo
        from .followup_portable import export_followup
        from .pmf_portable import export_research
        from .audit_portable import export_archives
        readers={'learning':export_learning,'payments':export_payments,'storekit':export_storekit,
                 'attribution':export_attribution,'aeo':export_aeo,'followup':export_followup,
                 'pmf_research':export_research,'inspection_history':export_archives}
        result={}
        for name,reader in readers.items():
            with connection(self.path) as db:result[name]=reader(db,app_id)
        return result

    def _export_files(self,app_id,records):
        files={}
        for record in records:
            file_id=record["data"].get("file_id") if record["kind"]=="asset" else None
            if file_id:
                if not re.fullmatch(r"[a-f0-9-]+\.(?:png|jpg|jpeg)",file_id):
                    raise Invalid("Asset has an invalid local file identifier")
                path=self.path.parent/"files"/app_id/file_id
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=record["data"]["sha256"]:
                    raise Invalid("Asset integrity changed; resolve it before exporting")
                files[file_id]={"id":file_id,"sha256":record["data"]["sha256"],"base64":base64.b64encode(raw).decode()}
        return list(files.values())

    def restore(self, body):
        """Verify a snapshot and refuse conflict or cross-app overwrites."""
        payload = body.get("payload")
        if not isinstance(payload,dict) or body.get("sha256") != digest(payload):
            raise Invalid("Snapshot integrity check failed")
        if payload.get("schema") != "growth.snapshot.v1":
            raise Invalid("Snapshot schema not recognized")
        app = payload["app"]
        app_id = identifier(app["id"])
        records = payload.get("records")
        if not isinstance(records,list) or len(records)>1000:
            raise Invalid("Snapshot may contain at most 1000 records")
        if any(r.get("app_id")!=app_id for r in records):
            raise Invalid("Snapshot contains another app's evidence")
        data = app_data(app["data"])
        files=self._restore_files(payload.get("files",[]),records)
        self._commit_restore(app_id,data,records,files,payload.get("ledger"),payload.get("experiments"),payload.get("schedules"),payload.get("references"),payload.get("production"),payload.get("rankings"),payload.get("acquisition"),payload.get("media"),payload.get("learning"),payload.get("payments"),payload.get("storekit"),payload.get("capabilities"),payload.get("attribution"),payload.get("aeo"),payload.get("followup"),payload.get("pmf_research"),payload.get("inspection_history"))
        return self.app(app_id)

    def _commit_restore(self,app_id,data,records,files,ledger=None,experiments=None,schedules=None,references=None,production=None,rankings=None,acquisition=None,media=None,learning=None,payments=None,storekit=None,capabilities=None,attribution=None,aeo=None,followup=None,pmf_research=None,inspection_history=None):
        """Commit records only after exclusive file writes, cleaning owned files on failure."""
        from .learning_portable import restore_learning
        from .payment_portable import restore_payments
        from .storekit_portable import restore_storekit
        from .attribution_portable import restore_attribution
        from .aeo_portable import restore_aeo
        from .followup_portable import restore_followup
        from .pmf_portable import restore_research
        from .audit_portable import restore_archives
        folder=self.path.parent/"files"/app_id
        created=[]
        try:
            with connection(self.path) as db:
                self._restore(db,app_id,data,records)
                restore_ledger(db,app_id,ledger)
                restore_experiments(db,app_id,experiments)
                restore_schedules(db,app_id,schedules)
                restore_library(db,app_id,references)
                restore_capabilities(db,app_id,capabilities)
                restore_production(db,app_id,production)
                restore_rankings(db,app_id,rankings)
                restore_acquisition(db,app_id,acquisition)
                restore_learning(db,app_id,learning)
                restore_payments(db,app_id,payments)
                restore_storekit(db,app_id,storekit)
                restore_attribution(db,app_id,attribution)
                restore_aeo(db,app_id,aeo)
                restore_followup(db,app_id,followup)
                restore_research(db,app_id,pmf_research)
                restore_archives(db,app_id,inspection_history)
                video_files=restore_media(db,app_id,media)
                self._write_media(app_id,video_files,created)
                folder.mkdir(parents=True,exist_ok=True)
                for file_id,raw in files.items():
                    path=folder/file_id
                    with path.open("xb") as output:
                        created.append(path)
                        output.write(raw)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise

    def _write_media(self,app_id,files,created):
        """Write only validated exclusive media files in this restore transaction."""
        folder=self.path.parent/"renders"/app_id
        if files:folder.mkdir(parents=True,exist_ok=True)
        for render_id,raw in files.items():
            path=folder/(render_id+".mp4")
            with path.open("xb") as output:created.append(path);output.write(raw)

    def _restore_files(self,items,records):
        if not isinstance(items,list) or len(items)>1000:
            raise Invalid("Invalid snapshot file manifest")
        files={}
        for item in items:
            file_id=item.get("id","")
            if not re.fullmatch(r"[a-f0-9-]+\.(?:png|jpg|jpeg)",file_id) or file_id in files:
                raise Invalid("Invalid or duplicate snapshot file identifier")
            raw=base64.b64decode(item.get("base64",""),validate=True)
            if len(raw)>8388608 or hashlib.sha256(raw).hexdigest()!=item.get("sha256"):
                raise Invalid("Snapshot file integrity or size check failed")
            files[file_id]=raw
        required_files={r["data"].get("file_id") for r in records if r.get("kind")=="asset"}
        if required_files!=set(files):
            raise Invalid("Snapshot file manifest must match its asset records exactly")
        for record in records:
            if record.get("kind")=="asset":
                raw=files[record["data"]["file_id"]]
                if hashlib.sha256(raw).hexdigest()!=record["data"].get("sha256"):
                    raise Invalid("Snapshot asset evidence does not match its file bytes")
        return files

    def _restore(self, db, app_id, data, records):
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT id FROM apps WHERE id=?",(app_id,)).fetchone():
            raise Invalid("Workspace already exists; restore into an empty database to avoid overwriting")
        db.execute("INSERT INTO apps(id,data,updated) VALUES(?,?,?)",(app_id,canonical(data),now()))
        for record in records:
            if record.get("kind") not in FIELDS:
                raise Invalid("Snapshot contains unknown evidence type")
            safe_data(record["data"])
            if record["hash"]!=digest({"kind":record["kind"],"data":record["data"],"source":record["source"]}):
                raise Invalid("Evidence hash mismatch")
            self._write_record(db,app_id,record["id"],record["kind"],record["title"],record["source"],record["data"],"restored",None)
        audit(db,app_id,"workspace.restored",{"records":len(records)})
