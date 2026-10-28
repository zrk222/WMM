"""Durable local queue. Expired leases resume; no provider mutations occur."""
import json
import threading
import time
from urllib.error import HTTPError, URLError
from .common import Invalid, canonical, digest, now, required, uid
from .db import connection
from .pipeline import execute
from .providers import sync
from .ledger import Ledger
from .provider_reports import PreparedAppleMetrics, read_report
from .experiments import Experiments
from .experiment_schedules import Schedules
from .insights import Insights
from .followup import Followup
from .automation_health import Supervision


def enqueue(store,app_id,action,data,request_key):
    """Persist an idempotent app-scoped job while rejecting a reused key with different input."""
    store.app(app_id)
    if action not in ("pipeline","sync","render","hypit_render","edit_render","drive_import"):
        raise Invalid("Unknown job action")
    request_key=required(request_key,"Request key",120)
    with connection(store.path) as db:
        inserted=db.execute("INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",(uid(),app_id,action,canonical(data),"QUEUED",now(),now(),request_key)).rowcount
        row=db.execute("SELECT * FROM jobs WHERE app_id=? AND request_key=?",(app_id,request_key)).fetchone()
        if row["action"]!=action or row["data"]!=canonical(data):
            raise Invalid("Request key already used for a different job")
        result=json_job(row)
        from .automation_execution import attach_job
        attach_job(db,result,bool(inserted))
        return result


def json_job(row):
    """Decode durable job input and result fields for the API."""
    result=dict(row)
    result["data"]=json.loads(result["data"])
    result["result"]=json.loads(result["result"]) if result["result"] else None
    return result


def jobs(store,app_id):
    """Return bounded recent runs for one workspace."""
    store.app(app_id)
    with connection(store.path) as db:
        return [json_job(r) for r in db.execute("SELECT * FROM jobs WHERE app_id=? AND action!='drive_import' ORDER BY created DESC LIMIT 100",(app_id,))]


def claim(store):
    """Atomically lease one queued or expired job within the retry limit."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE jobs SET status='FAILED',result=?,updated=? WHERE status='RUNNING' AND lease<? AND attempts>=3",(canonical({"error":"Recovery attempt limit reached; review the job before retry"}),now(),time.time()))
        row=db.execute("SELECT * FROM jobs WHERE (status='QUEUED' OR (status='RUNNING' AND lease<?)) AND attempts<3 ORDER BY created LIMIT 1",(time.time(),)).fetchone()
        if not row:
            return None
        db.execute("UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease=?,updated=? WHERE id=?",(time.time()+60,now(),row["id"]))
        claimed=json_job(row);claimed["attempts"]+=1
        return claimed


def process(store,job,stop=None):
    """Prepare local packets or perform a configured read-only provider request."""
    if job['action']=='agent_run':
        from .agent_tasks import execute as agent_execute
        return agent_execute(store,job,stop)
    if job['action'] in ('drive_import','hypit_render','edit_render','render'):
        return process_media(store,job,stop)
    app=store.app(job["app_id"])
    records=store.records(app["id"])
    if job["action"]=="experiment":
        return Experiments(store).evaluate(app["id"],job["data"]["experiment_id"],scheduled=job["data"])
    if job['action'] in ('resolution','experiment_tracking'):
        return process_evidence_job(store,job)
    if job["action"]=="pipeline":
        from .subscription_readiness import readiness
        from .connection_setup import Connections
        catalog=readiness(app,records,jobs(store,app['id']),Connections(store).statuses(app['id']))
        from .release_readiness import readiness as release_readiness
        release=release_readiness(app,records,jobs(store,app['id']),Connections(store).statuses(app['id']))
        from .workflow_telemetry import emit
        return execute(app,records,job["data"].get("stage",0),Ledger(store.path).reports(app["id"]),catalog,release,
                       progress=lambda code,stage:emit(store,job,code,stage))
    binding=current_connection(store,app["id"],job["data"])["data"]
    if 'analytics_schedule_id' in job['data']:
        from .apple_metrics_schedule import check_scheduled
        check_scheduled(store,job)
    from .credential_vault import namespace
    binding={**binding,"_vault_namespace":namespace(store.path)}
    if "options" in job["data"]:
        if job['data']['options'].get('operation')=='subscription_catalog':
            from .subscription_readiness import validate_catalog_scope
            validate_catalog_scope(app,binding)
        result=read_report(binding,app["id"],job["data"]["options"],
            connection_id=job["data"].get("connection_id"),
            connection_version=job["data"].get("connection_version"))
    else:
        result=sync(binding,app["id"])
    current_connection(store,app["id"],job["data"])
    if 'analytics_schedule_id' in job['data']:
        from .apple_metrics_schedule import check_scheduled
        check_scheduled(store,job)
    return result


def _persist_prepared_apple_metrics(db,store,job,prepared):
    """Commit local partitions only with the still-leased job completion."""
    db.execute('BEGIN IMMEDIATE')
    current=db.execute('SELECT action,data,status,attempts,lease FROM jobs WHERE id=? AND app_id=?',
        (job['id'],job['app_id'])).fetchone()
    if (current is None or current['action']!='sync' or current['status']!='RUNNING'
            or current['attempts']!=job['attempts'] or current['lease']<time.time()
            or json.loads(current['data'])!=job['data']):
        return None,None
    try:
        if 'analytics_schedule_id' in job['data']:
            from .apple_metrics_schedule import check_scheduled_db
            check_scheduled_db(db,job)
        identity=prepared.identity
        if (identity['app_id']!=job['app_id']
                or identity['connection_id']!=job['data'].get('connection_id')
                or identity['connection_version']!=job['data'].get('connection_version')):
            raise Invalid('Apple analytics result no longer matches the leased app connection')
        connection=db.execute('SELECT version,data FROM records WHERE app_id=? AND id=? AND kind=?',
            (job['app_id'],identity['connection_id'],'connection')).fetchone()
        if connection is None or connection['version']!=identity['connection_version']:
            raise Invalid('Apple analytics connection changed before persistence')
        binding=json.loads(connection['data'])
        if (digest(binding)!=prepared.connection_hash or binding.get('provider')!='app_store'
                or str(binding.get('store_app_id'))!=identity['store_app_id']):
            raise Invalid('Apple analytics source changed before persistence')
        app_row=db.execute('SELECT id,data,version FROM apps WHERE id=?',(job['app_id'],)).fetchone()
        if app_row is None:
            raise Invalid('Apple analytics app was removed before persistence')
        app=dict(app_row);app['data']=json.loads(app['data'])
        if ('manifest_version' in job['data'] and job['data']['manifest_version']!=app['version']):
            raise Invalid('Apple analytics app changed before persistence')
        if 'agent_policy_sha256' in job['data']:
            from .marketing_agent_manifest import authorize_read
            authorize_read(app,binding,job['data'])

        from .apple_metrics_store import _reconcile
        db.execute('SAVEPOINT apple_metrics_job')
        try:
            statuses=[_reconcile(db,item['partition'],item['instance'])
                      for item in prepared.partitions]
            db.execute('RELEASE SAVEPOINT apple_metrics_job')
        except BaseException:
            db.execute('ROLLBACK TO SAVEPOINT apple_metrics_job')
            db.execute('RELEASE SAVEPOINT apple_metrics_job')
            raise
        return prepared.summary(statuses),'SUCCEEDED'
    except Invalid as exc:
        return dict(error=str(exc),next_action='Refresh the report selection or connection, then retry the read',
                    external_execution='READ_COMPLETED_NO_METRIC_PARTITIONS_WRITTEN'),'BLOCKED'
    except Exception:
        return dict(error='Apple analytics observations could not be saved.',
                    next_action='Review local storage and the worker status before retrying',
                    external_execution='READ_COMPLETED_NO_METRIC_PARTITIONS_WRITTEN'),'BLOCKED'


def process_media(store,job,stop):
    """Keep local media worker dispatch explicit without widening generic queue authority."""
    from .drive_import_jobs import Imports
    from .hypit_jobs import HypitRenders
    from .video_edit_jobs import EditRenders
    from .creative_rendering import Renders
    handlers={'drive_import':Imports,'hypit_render':HypitRenders,'edit_render':EditRenders,'render':Renders}
    return handlers[job['action']](store).execute(job,stop)


def process_evidence_job(store,job):
    """Keep exact-approved tracking and resolution dispatch outside generic provider reads."""
    if job['action']=='experiment_tracking':
        from .experiment_tracking import Tracking
        return Tracking(store).execute(job)
    from .resolution_tools import execute as resolve
    from .sequence_jobs import callback
    on_job=callback(store,job)
    return resolve(store,job['app_id'],job['data'],on_job) if on_job is not None else resolve(store,job['app_id'],job['data'])


def current_connection(store,app_id,data):
    """Prevent queued or in-flight reads from accepting a rotated connection."""
    if 'manifest_version' in data and store.app(app_id)['version'] != data['manifest_version']:
        raise Invalid('App changed after collection was prepared; refresh campaign inputs')
    record=next((r for r in store.records(app_id) if r["id"]==data.get("connection_id") and r["kind"]=="connection"),None)
    if record is None or type(data.get("connection_version")) is not int or record["version"]!=data["connection_version"]:
        raise Invalid("Connection changed or this older run lacks its version; reopen the report and rerun")
    if record['data'].get('provider')=='google_play':
        from .play_contract import require_target
        if type(data.get('manifest_version')) is not int:
            raise Invalid('Google Play read lacks its approved app version; reopen the read')
        require_target(store.app(app_id),record['data'])
    if 'agent_policy_sha256' in data:
        from .marketing_agent_manifest import authorize_read
        authorize_read(store.app(app_id),record['data'],data)
    return record


def failed_result(job,error):
    """Only already-permitted transient source reads get the existing bounded retry."""
    if job['action']=='drive_import':
        return dict(error='Drive import stopped at a source, permission or validation boundary.',
                    next_action='Inspect the private Drive import and reconnect, review or retry explicitly.',
                    external_execution='READ_ATTEMPT_MAY_HAVE_OCCURRED'),'BLOCKED',0
    if job['action']=='sync' and 'analytics_schedule_id' in job['data']:
        if transient_read_error(error) and job['attempts']<3:
            delay=5*job['attempts']
            return dict(status='RETRY_WAIT',summary='Transient scheduled Apple read failure; bounded retry queued',
                attempt=job['attempts'],retry_in_seconds=delay,
                next_action='The worker will retry this same owner-enabled read within its three-attempt limit',
                external_execution='READ_RETRY_PENDING'),'RUNNING',delay
        return dict(error='Scheduled Apple analytics read failed; review the connection and latest job result',
            next_action='Open the Apple analytics schedule, review the failure, and reconnect or resume explicitly',
            external_execution='READ_ATTEMPT_MAY_HAVE_OCCURRED'),'BLOCKED',0
    result={'error':str(error),'next_action':'Review inputs or connection, then create a new run','external_execution':'NOT_RUN'}
    if job['action']!='sync' or 'agent_policy_sha256' not in job['data'] or job['attempts']>=3:
        return result,'BLOCKED',0
    if not transient_read_error(error):return result,'BLOCKED',0
    delay=5*job['attempts']
    return dict(status='RETRY_WAIT',summary='Transient provider read failure; safe retry scheduled',
        attempt=job['attempts'],retry_in_seconds=delay,
        next_action='Worker will retry this same approved read within its three-attempt limit',
        external_execution='READ_RETRY_PENDING'),'RUNNING',delay


def run_once(store,stop=None):
    """Complete one leased job without overwriting cancellation or hiding failure."""
    from .sequence_runtime import advance
    from .sequence_jobs import guard_owned
    progressed=advance(store)
    job=claim(store)
    if not job:
        return progressed
    retry_delay=0
    try:
        guard_owned(store,job)
        from .automation_execution import job_execution
        with job_execution(store,job):
            from .workflow_telemetry import emit
            emit(store,job,'STARTED')
            result=process(store,job) if stop is None else process(store,job,stop)
        guard_owned(store,job)
        status="SUCCEEDED"
    except Exception as exc:
        result,status,retry_delay=failed_result(job,exc)
    with connection(store.path) as db:
        if isinstance(result,PreparedAppleMetrics):
            result,status=_persist_prepared_apple_metrics(db,store,job,result)
            if status is None:
                return True
        changed=db.execute("UPDATE jobs SET status=?,result=?,lease=?,updated=? WHERE id=? AND status='RUNNING' AND attempts=?",(status,canonical(result),time.time()+retry_delay if retry_delay else 0,now(),job["id"],job["attempts"])).rowcount
        if changed:
            from .workflow_telemetry import append
            append(db,job,'RETRY_WAIT' if retry_delay else status)
            if 'analytics_schedule_id' in job['data']:
                from .apple_metrics_schedule import complete_job
                complete_job(db,job,result,status)
            if job['action']=='agent_run':
                from .agent_tasks import complete as agent_complete
                agent_complete(db,job,result,status)
            db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(job["app_id"],"job."+status.lower(),canonical({"id":job["id"],"action":job["action"],"result_hash":digest(result)}),now()))
    return True


def transient_read_error(error):
    """Retry typed transport failures only; never infer permission from error text."""
    seen=set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error,HTTPError):
            return error.code in (408,429,500,502,503,504)
        if isinstance(error,(URLError,TimeoutError,ConnectionError)):
            return True
        error=error.__cause__
    return False


class Runner:
    def __init__(self,store):
        self.store=store
        self.stop_event=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True,name="growth-worker")
        self.supervision=Supervision()

    @property
    def health(self):
        return self.supervision.snapshot()

    def retry_failed(self):
        """Request recovery without re-enabling app policy or replaying failed jobs."""
        self.supervision.retry.set()
        return {"status":"RETRY_REQUESTED","scope":"SHARED_LOCAL_WORKER_FAILED_COMPONENTS_ONLY"}

    def run(self):
        """Poll the durable queue until the local runner is stopped."""
        while not self.stop_event.is_set():
            if not self.poll():
                self.stop_event.wait(0.25)

    def poll(self):
        """Isolate failures so unrelated schedules and the durable queue continue."""
        if self.stop_event.is_set():
            return False
        self.supervision.begin()
        self.supervision.attempt("experiments",lambda:Schedules(self.store).tick(),1)
        self.supervision.attempt("analytics",lambda:Insights(self.store).tick(),1)
        from .apple_metrics_schedule import AppleMetricsSchedules
        self.supervision.attempt("apple_metrics",lambda:AppleMetricsSchedules(self.store).tick(),1)
        self.supervision.attempt("followup",lambda:Followup(self.store).tick(),1)
        from .social_renewal import Renewal
        self.supervision.attempt("social",lambda:Renewal(self.store).tick(),60)
        worked=self.supervision.attempt("queue",lambda:run_once(self.store,self.stop_event))
        self.supervision.finish()
        return worked

    def start(self):
        """Start the local worker thread without enabling provider writes."""
        self.thread.start()

    def stop(self):
        """Stop polling and join the worker with a bounded wait."""
        self.stop_event.set()
        self.thread.join(timeout=20)
        if not self.thread.is_alive():
            self.supervision.stopped()
