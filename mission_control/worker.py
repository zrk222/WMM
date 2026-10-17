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
from .provider_reports import read_report
from .experiments import Experiments
from .experiment_schedules import Schedules
from .insights import Insights
from .followup import Followup
from .automation_health import Supervision


def enqueue(store,app_id,action,data,request_key):
    """Persist an idempotent app-scoped job while rejecting a reused key with different input."""
    store.app(app_id)
    if action not in ("pipeline","sync","render"):
        raise Invalid("Unknown job action")
    request_key=required(request_key,"Request key",120)
    with connection(store.path) as db:
        db.execute("INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",(uid(),app_id,action,canonical(data),"QUEUED",now(),now(),request_key))
        row=db.execute("SELECT * FROM jobs WHERE app_id=? AND request_key=?",(app_id,request_key)).fetchone()
        if row["action"]!=action or row["data"]!=canonical(data):
            raise Invalid("Request key already used for a different job")
        return json_job(row)


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
        return [json_job(r) for r in db.execute("SELECT * FROM jobs WHERE app_id=? ORDER BY created DESC LIMIT 100",(app_id,))]


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
    app=store.app(job["app_id"])
    records=store.records(app["id"])
    if job["action"]=="render":
        from .creative_rendering import Renders
        return Renders(store).execute(job,stop)
    if job["action"]=="experiment":
        return Experiments(store).evaluate(app["id"],job["data"]["experiment_id"],scheduled=job["data"])
    if job['action']=='resolution':
        from .resolution_tools import execute as resolve
        return resolve(store,app['id'],job['data'])
    if job["action"]=="pipeline":
        from .subscription_readiness import readiness
        from .connection_setup import Connections
        catalog=readiness(app,records,jobs(store,app['id']),Connections(store).statuses(app['id']))
        from .release_readiness import readiness as release_readiness
        release=release_readiness(app,records,jobs(store,app['id']),Connections(store).statuses(app['id']))
        return execute(app,records,job["data"].get("stage",0),Ledger(store.path).reports(app["id"]),catalog,release)
    binding=current_connection(store,app["id"],job["data"])["data"]
    from .credential_vault import namespace
    binding={**binding,"_vault_namespace":namespace(store.path)}
    if "options" in job["data"]:
        if job['data']['options'].get('operation')=='subscription_catalog':
            from .subscription_readiness import validate_catalog_scope
            validate_catalog_scope(app,binding)
        result=read_report(binding,app["id"],job["data"]["options"])
    else:
        result=sync(binding,app["id"])
    current_connection(store,app["id"],job["data"])
    return result


def current_connection(store,app_id,data):
    """Prevent queued or in-flight reads from accepting a rotated connection."""
    if 'manifest_version' in data and store.app(app_id)['version'] != data['manifest_version']:
        raise Invalid('App changed after collection was prepared; refresh campaign inputs')
    record=next((r for r in store.records(app_id) if r["id"]==data.get("connection_id") and r["kind"]=="connection"),None)
    if record is None or type(data.get("connection_version")) is not int or record["version"]!=data["connection_version"]:
        raise Invalid("Connection changed or this older run lacks its version; reopen the report and rerun")
    if 'agent_policy_sha256' in data:
        from .marketing_agent_manifest import authorize_read
        authorize_read(store.app(app_id),record['data'],data)
    return record


def run_once(store,stop=None):
    """Complete one leased job without overwriting cancellation or hiding failure."""
    job=claim(store)
    if not job:
        return False
    retry_delay=0
    try:
        result=process(store,job) if stop is None else process(store,job,stop)
        status="SUCCEEDED"
    except Exception as exc:
        result={"error":str(exc),"next_action":"Review inputs or connection, then create a new run","external_execution":"NOT_RUN"}
        status="BLOCKED"
        if job['action']=='sync' and 'agent_policy_sha256' in job['data'] and job['attempts']<3 and transient_read_error(exc):
            retry_delay=5*job['attempts']
            status='RUNNING'
            result={'status':'RETRY_WAIT','summary':'Transient provider read failure; safe retry scheduled',
                    'attempt':job['attempts'],'retry_in_seconds':retry_delay,
                    'next_action':'Worker will retry this same approved read within its three-attempt limit',
                    'external_execution':'READ_RETRY_PENDING'}
    with connection(store.path) as db:
        changed=db.execute("UPDATE jobs SET status=?,result=?,lease=?,updated=? WHERE id=? AND status='RUNNING' AND attempts=?",(status,canonical(result),time.time()+retry_delay if retry_delay else 0,now(),job["id"],job["attempts"])).rowcount
        if changed:
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
