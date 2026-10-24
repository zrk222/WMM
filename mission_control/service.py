"""Application service for workspaces, evidence, review packets and exports."""
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import hashlib
from .common import Invalid, amount, canonical, digest, iso_time, now, required, uid
from .db import connection
from .catalog import FIELDS, LABELS, PROVIDERS
from .pipeline import evaluate
from .automatic_preparation import prepare
from .metrics import summarize, cohort_metrics, retention_metrics, acquisition_metrics
from .worker import enqueue, jobs
from .ledger import Ledger
from .provider_reports import report_options
from .connection_setup import Connections
from .review_access import Access
from .verified_reviews import Reviews
from .provider_outbox import Outbox
from .outcome_learning import Learning
from .signed_payments import Payments
from .insights import Insights
from .storekit_ingestion import Notifications
from .experiments import Experiments
from .experiment_schedules import Schedules
from .creative_library import Library
from .creative_analysis import Analyses
from .creative_briefs import Briefs
from .creative_ranking import Rankings
from .acquisition_workflows import Acquisition
from .creative_rendering import Renders
from .hypit_jobs import HypitRenders
from .guided_workflow import guide
from .workflow_automation import recommend
from .subscription_readiness import readiness as catalog_readiness, validate_catalog_scope
from .release_readiness import readiness as release_readiness


def validate_evidence(kind, data, app_id):
    """Validate field presence before kind-specific arithmetic and typed values."""
    if kind not in FIELDS or not isinstance(data,dict):
        raise Invalid("Choose an evidence type and enter an object")
    missing=[k for k in FIELDS[kind] if data.get(k) is None or data.get(k)==""]
    if missing:
        raise Invalid("Complete these fields: "+", ".join(missing))
    validators={"cohort":cohort_metrics,"retention":retention_metrics,
                "acquisition":lambda d:acquisition_metrics(d["analysis"],app_id)}
    if kind in validators:
        validators[kind](data)
    validate_values(data)
    if kind=="readiness":
        from .journey_readiness import validate
        validate(data)
    if kind=="connection":
        validate_binding(data,app_id)


def validate_values(data):
    """Reject invalid amounts and ambiguous timestamps before saving evidence."""
    for field in ("budget_minor","daily_cap_minor","price_minor","p0_count","amount_minor"):
        if field in data:
            amount(data[field],field)
    for field in ("checked_at","occurred_at"):
        if field in data:
            iso_time(data[field])
    flags=("authentic","rights_cleared","consent_review","refund_reconciliation","installed","fresh_install","signed_out","restore_tested","trial_eligibility_tested","mature","confirmed")
    for field in flags:
        if field in data and type(data[field]) is not bool:
            raise Invalid(f"{field}: choose Yes or No")


def validate_binding(data, app_id):
    """Require an app-specific environment name and a known read-only provider."""
    if "_vault_namespace" in data:
        raise Invalid("Runtime protected scope cannot be supplied in evidence")
    if data.get('provider')=='google_play':
        from .play_contract import connection_metadata
        connection_metadata(data)
        return
    if data["provider"] not in ("apple_ads","app_store"):
        raise Invalid("Use Google Play, Apple Ads or App Store Connect; answer-engine observations use import")
    if data.get("credential_ref"):
        if not re.fullmatch(r"[a-f0-9-]{36}",str(data["credential_ref"])) or data.get("auth_mode") not in ("managed_key","disconnected"):
            raise Invalid("Protected connection metadata is invalid; use guided setup")
        return
    prefix="GROWTH_"+app_id.upper().replace("-","_")+"_"
    if not re.fullmatch(prefix+r"[A-Z0-9_]+",str(data.get("env_ref",""))):
        raise Invalid("Use an environment variable name beginning "+prefix)


class Service:
    def __init__(self,store,operator="local-operator"):
        self.store=store
        self.operator=operator

    def workspace(self,app_id):
        """Assemble the selected app dashboard from its own records and runs."""
        from .production_feasibility import Capabilities
        from .attribution_ingestion import Observations
        from .aeo_workflows import Checks
        from .followup import Followup
        from .public_store_readback import PublicStore
        from .pmf_workflow import prepare as prepare_pmf
        from .pmf_research import Research
        from .audit_runtime import Inspections
        from .measurement_integrity import view as measurement_integrity
        from .campaign_inputs import CampaignInputs
        app=self.store.app(app_id)
        records=self.store.records(app_id)
        ledger=Ledger(self.store.path).reports(app_id)
        schedules=Schedules(self.store).list(app_id)
        job_rows=jobs(self.store,app_id)
        connection_statuses=Connections(self.store).statuses(app_id)
        catalog=catalog_readiness(app,records,job_rows,connection_statuses)
        release=release_readiness(app,records,job_rows,connection_statuses)
        evaluated=evaluate(app,records,ledger,catalog,release)
        workflow=guide(app,records,evaluated,ledger,catalog,release)
        automation=recommend(app,records,ledger,workflow)
        preparation=prepare(app,records,ledger,catalog,release)
        preparation['release_inventory']=release
        preparation["recommendations"]=automation
        preparation['collection']=CampaignInputs(self.store).preview(app_id)
        research=Research(self.store).list(app_id)
        workspace={"app":app,"measurement_integrity":measurement_integrity(self.store,app_id),"subscription_catalog":catalog,"release_inventory":release,"inspections":Inspections(self.store).view(app_id),"workflow":workflow,"automation":automation,"pmf":prepare_pmf(app,records,ledger,research=research),"public_store_checks":PublicStore(self.store).list(app_id),"followup":Followup(self.store).list(app_id),"aeo":Checks(self.store).list(app_id),"records":records,"preparation":preparation,"stages":evaluated,"metrics":summarize(records,app_id,ledger),
                "jobs":job_rows,"audit":self.store.history(app_id),"approvals":self.approvals(app_id),"ledger":ledger,"capabilities":Capabilities(self.store).list(app_id),
                "connections":connection_statuses,"insights":Insights(self.store).list(app_id),"storekit":Notifications(self.store).list(app_id),"attribution":Observations(self.store).list(app_id),"experiments":Experiments(self.store).list(app_id),
                "schedules":schedules,"worker":getattr(self,"worker_health",lambda:{"status":"NOT_STARTED"})(),
                "references":Library(self.store).list(app_id),"analyses":Analyses(self.store).list(app_id),"briefs":Briefs(self.store).list(app_id),"rankings":Rankings(self.store).list(app_id),"acquisition":Acquisition(self.store).list(app_id),"renders":Renders(self.store).list(app_id),"access":dict(Access(self.store).list(app_id),external_execution="EXPLICIT_APP_STORE_PROMOTIONAL_TEXT_ONLY"),"verified_reviews":Reviews(self.store).list(app_id),"provider_actions":Outbox(self.store).list(app_id),"learning":Learning(self.store).list(app_id),"payments":Payments(self.store).list(app_id)}
        from .resolution_plan import prepare as prepare_resolutions
        from .resolutions import Resolutions
        from .agent_feedback import reuse_candidate
        workspace['resolutions']=prepare_resolutions(app,records,workflow,preparation['collection'],workspace['insights'],workspace['experiments'],reuse_candidate(self.store,app))
        workspace['hypit_renders']=HypitRenders(self.store).list(app_id)
        workspace['resolutions']['history']=Resolutions(self.store,self.operator).history(app_id)
        from .sequence_plan import prepare as prepare_sequence
        from .sequence_store import Sequences
        workspace['sequences']=dict(proposal=prepare_sequence(app,workspace['resolutions'],preparation['collection']),
                                   history=Sequences(self.store,self.operator).history(app_id))
        from .experiment_tracking import Tracking
        workspace['experiment_tracking']=Tracking(self.store).list(app_id)
        from .agent_access import AgentAccess
        workspace['agent_access']=AgentAccess(self.store).view(app_id)
        from .social_http import view as social_view
        workspace['social_access']=social_view(self.store,app_id)
        from .play_connections import PlayConnections
        workspace['play']=PlayConnections(self.store).status(app_id)
        from .setup_discovery import SetupDiscovery
        workspace['setup_discovery']=SetupDiscovery(self.store).list(app_id)
        workspace['subscription_growth']=self.subscription_review(app_id,expected=app)
        return workspace

    def subscription_review(self,app_id,expected=None):
        """Expose the integrated source-bound review without granting execution authority."""
        from .subscription_review import review_status
        return review_status(self.store,app_id,expected=expected)

    def cohort(self,app_id,body):
        """Register the selected app's immutable cohort observation contract."""
        self.store.app(app_id)
        return Ledger(self.store.path).define(app_id,body)

    def events(self,app_id,body):
        """Import permitted export rows through the selected workspace boundary."""
        self.store.app(app_id)
        return Ledger(self.store.path).ingest(app_id,body)

    def bootstrap(self):
        """Return app choices and UI contracts with truthful local execution limits."""
        from .credential_vault import namespace
        return {"apps":self.store.apps(),"fields":FIELDS,"labels":LABELS,"providers":PROVIDERS,
                "workspace_instance_id":namespace(self.store.path),
                "operator":self.operator,"mode":"LOCAL_WORKSTATION","external_writes":"EXPLICIT_ACTION_APPROVAL_REQUIRED","automatic_external_writes":False,"explicit_action_capability":"APP_STORE_PROMOTIONAL_TEXT_ONLY","authorized_spend_minor":0,"startup_build_id":getattr(self,"build_id",None)}

    def evidence(self,app_id,body):
        """Validate a typed record and verify local asset bytes before its versioned save."""
        validate_evidence(body.get("kind"),body.get("data"),app_id)
        if body["kind"]=="asset":
            self._validate_asset(app_id,body["data"])
        return self.store.save_record(app_id,body)

    def _validate_asset(self,app_id,data):
        file_id=data.get("file_id","")
        if not re.fullmatch(r"[a-f0-9-]+\.(?:png|jpg|jpeg)",file_id):
            raise Invalid("Upload this image in this workspace before registering it")
        path=self.store.path.parent/"files"/app_id/file_id
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=data.get("sha256"):
            raise Invalid("Asset file is missing or its hash changed. Upload it again.")

    def queue(self,app_id,body):
        """Validate the requested stage or connection before durable job submission."""
        if body.get("action") in ("render","hypit_render"):raise Invalid("Use the guided render workflow to validate source proof first")
        if not isinstance(body.get("data",{}),dict):
            raise Invalid("Job data must be an object")
        if body.get("action")=="pipeline":
            stage=body.get("data",{}).get("stage",0)
            if type(stage) is not int or not 0<=stage<=12:
                raise Invalid("Choose a stage from 1 to 12, or 0 for all stages")
        if body.get("action")=="sync":
            body={**body,'data':self.sync_data(app_id,body['data'])}
        return enqueue(self.store,app_id,body.get("action"),body.get("data",{}),body.get("request_key"))

    def sync_data(self,app_id,data):
        """Validate the exact current connection and report before durable submission."""
        binding=next((row for row in self.store.records(app_id) if row['id']==data.get('connection_id') and row['kind']=='connection'),None)
        if not binding:
            raise Invalid('Choose a saved connection in this workspace')
        version=data.get('connection_version',binding['version'])
        if type(version) is not int or version!=binding['version']:
            raise Invalid('Connection changed; reopen the report from this workspace')
        if binding['data'].get('provider')=='google_play':
            data=self.play_sync_data(app_id,binding,data)
        if 'options' in data:
            report_options(binding['data']['provider'],data['options'])
            if data['options']['operation']=='subscription_catalog':
                validate_catalog_scope(self.store.app(app_id),binding['data'])
        return {**data,'connection_version':version}

    def play_sync_data(self,app_id,binding,data):
        """Manual and agent reads require the same approved Android target and current app version."""
        from .play_contract import require_target
        app=self.store.app(app_id);require_target(app,binding['data'])
        version=data.get('manifest_version',app['version'])
        if type(version) is not int or version!=app['version']:
            raise Invalid('App changed; reopen Google Play read setup')
        return dict(data,manifest_version=version,options=data.get('options',{'operation':'play_releases'}))

    def cancel(self,app_id,job_id):
        """Cancel only an active job in the selected workspace."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            changed=db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE id=? AND app_id=? AND status IN ('QUEUED','RUNNING')",(now(),job_id,app_id)).rowcount
        if not changed:
            raise Invalid("This job cannot be cancelled; reload its current state")
        return {"status":"CANCELLED"}

    def approvals(self,app_id):
        """List immutable review packets scoped to one app."""
        from .store import decode
        with connection(self.store.path) as db:
            return [decode(r) for r in db.execute("SELECT * FROM approvals WHERE app_id=? ORDER BY created DESC",(app_id,))]

    def prepare_review(self,app_id,body):
        """Freeze a source record into an expiring manually executed review packet."""
        self.store.app(app_id)
        record=next((r for r in self.store.records(app_id) if r["id"]==body.get("record_id") and r["kind"] in ("distribution","store","experiment")),None)
        if not record:
            raise Invalid("Choose an existing distribution, store or experiment evidence record")
        packet={"app_id":app_id,"manifest_version":self.store.app(app_id)["version"],"record":record,"external_execution":"MANUAL_ONLY","authorized_spend_minor":0}
        review_id=uid()
        expires=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        with connection(self.store.path) as db:
            db.execute("INSERT INTO approvals(id,app_id,packet,hash,preparer,status,expires,created) VALUES(?,?,?,?,?,?,?,?)",(review_id,app_id,canonical(packet),digest(packet),self.operator,"WAITING_REVIEW",expires,now()))
        return {"id":review_id,"status":"WAITING_REVIEW"}

    def review(self,app_id,review_id,body):
        """Record a distinct reviewer after checking expiry, source integrity and replay."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            row=db.execute("SELECT * FROM approvals WHERE id=? AND app_id=?",(review_id,app_id)).fetchone()
            self._check_review(row,body)
            db.execute("UPDATE approvals SET checker=?,status='REVIEW_RECORDED' WHERE id=?",(self.operator,review_id))
        return {"status":"REVIEW_RECORDED","external_execution":"MANUAL_ONLY","identity_assurance":"Local operator identity is not internet-authenticated"}

    def _check_review(self,row,body):
        if not row or row["status"]!="WAITING_REVIEW":
            raise Invalid("Review packet is unavailable or already reviewed")
        if row["preparer"]==self.operator:
            raise Invalid("The preparer cannot review their own packet; use a separate reviewer workstation session")
        if iso_time(row["expires"])<datetime.now(timezone.utc):
            raise Invalid("Review expired; prepare a fresh packet")
        if body.get("hash")!=row["hash"] or digest(json.loads(row["packet"]))!=row["hash"]:
            raise Invalid("Review hash mismatch")
        record=json.loads(row["packet"])["record"]
        if self.store.app(row["app_id"])["version"]!=json.loads(row["packet"])["manifest_version"]:
            raise Invalid("App setup changed; prepare a fresh review packet")
        current=next((r for r in self.store.records(row["app_id"]) if r["id"]==record["id"]),None)
        if not current or current["hash"]!=record["hash"]:
            raise Invalid("Source evidence changed; prepare a fresh packet")

    def upload(self,app_id,filename,raw):
        """Store an image with its hash and unconfirmed authenticity and rights flags."""
        app=self.store.app(app_id)
        suffix=Path(filename).suffix.lower()
        allowed={".png":b"\x89PNG\r\n\x1a\n",".jpg":b"\xff\xd8\xff",".jpeg":b"\xff\xd8\xff"}
        if suffix not in allowed or not raw.startswith(allowed[suffix]):
            raise Invalid("Upload a PNG or JPEG image with matching file content")
        file_id=uid()+suffix
        folder=self.store.path.parent/"files"/app_id
        folder.mkdir(parents=True,exist_ok=True)
        (folder/file_id).write_bytes(raw)
        data={"release":app["data"].get("release"),"filename":Path(filename).name,"sha256":hashlib.sha256(raw).hexdigest(),
              "device":"REVIEW_REQUIRED","locale":app["data"].get("locale"),"authentic":False,"rights_cleared":False,"file_id":file_id}
        return self.store.save_record(app_id,{"kind":"asset","title":Path(filename).name,"source":"Local file upload; authenticity and rights require review","data":data})
