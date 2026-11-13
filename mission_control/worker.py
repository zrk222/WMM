"""Durable local queue. Expired leases resume; no provider mutations occur."""

import json
import threading
import time
from contextlib import nullcontext
from urllib.error import HTTPError, URLError

from .automation_health import Supervision
from .common import Invalid, canonical, digest, now, required, uid
from .db import connection
from .experiment_schedules import Schedules
from .experiments import Experiments
from .followup import Followup
from .insights import Insights
from .ledger import Ledger
from .pipeline import execute
from .provider_reports import PreparedAppleMetrics, read_report
from .providers import sync


def enqueue(store, app_id, action, data, request_key, *, commit_check=None):
    """Persist an idempotent app-scoped job while rejecting a reused key with different input."""
    store.app(app_id)
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        if commit_check is not None:
            commit_check(db)
        return enqueue_db(db, store, app_id, action, data, request_key)


def enqueue_db(db, store, app_id, action, data, request_key):
    """Queue using the caller's existing transaction and authority guards."""
    if not db.in_transaction:
        raise Invalid("Job admission requires an existing write transaction")
    if not db.execute("SELECT 1 FROM apps WHERE id=?", (app_id,)).fetchone():
        raise KeyError("App workspace not found")
    if action not in ("pipeline", "sync", "render", "hypit_render", "edit_render", "drive_import"):
        raise Invalid("Unknown job action")
    request_key = required(request_key, "Request key", 120)
    inserted = db.execute(
        "INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
        (uid(), app_id, action, canonical(data), "QUEUED", now(), now(), request_key),
    ).rowcount
    row = db.execute("SELECT * FROM jobs WHERE app_id=? AND request_key=?", (app_id, request_key)).fetchone()
    if row["action"] != action or row["data"] != canonical(data):
        raise Invalid("Request key already used for a different job")
    result = json_job(row)
    from .automation_execution import attach_job

    attach_job(db, result, bool(inserted))
    return result


def json_job(row):
    """Decode durable job input and result fields for the API."""
    result = dict(row)
    result["data"] = json.loads(result["data"])
    result["result"] = json.loads(result["result"]) if result["result"] else None
    return result


def jobs(store, app_id):
    """Return bounded recent runs for one workspace."""
    store.app(app_id)
    with connection(store.path) as db:
        return [
            json_job(r)
            for r in db.execute(
                "SELECT * FROM jobs WHERE app_id=? AND action!='drive_import' ORDER BY created DESC LIMIT 100",
                (app_id,),
            )
        ]


def claim(store):
    """Atomically lease one queued or expired job within the retry limit."""
    from .campaign_monitor import interrupted_result
    from .publication_schedule import initialize as publication_initialize

    publication_initialize(store)
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """UPDATE jobs SET status='BLOCKED',result=CASE WHEN action='campaign_monitor' THEN ? ELSE ? END,updated=?
            WHERE action IN ('campaign_post','campaign_ad','campaign_monitor') AND status='RUNNING' AND lease<?""",
            (
                canonical(interrupted_result()),
                canonical(
                    {
                        "error": "Scheduled post was interrupted; inspect its saved intent before any retry",
                        "external_execution": "UNKNOWN",
                    }
                ),
                now(),
                time.time(),
            ),
        )
        db.execute(
            "UPDATE publication_schedules SET status='BLOCKED',updated=? WHERE job_id IN (SELECT id FROM jobs WHERE action='social_publication' AND status='RUNNING' AND lease<?) AND status='QUEUED'",
            (now(), time.time()),
        )
        db.execute(
            "UPDATE jobs SET status='BLOCKED',result=?,updated=? WHERE action='social_publication' AND status='RUNNING' AND lease<?",
            (
                canonical(
                    {
                        "error": "Publication interrupted; reconcile the saved intent before another action",
                        "external_execution": "UNKNOWN",
                    }
                ),
                now(),
                time.time(),
            ),
        )
        db.execute(
            "UPDATE publication_schedules SET status='BLOCKED',updated=? WHERE job_id IN (SELECT id FROM jobs WHERE action='social_publication' AND status='QUEUED' AND attempts>=1000) AND status='QUEUED'",
            (now(),),
        )
        db.execute(
            "UPDATE jobs SET status='BLOCKED',result=?,updated=? WHERE action='social_publication' AND status='QUEUED' AND attempts>=1000",
            (
                canonical(
                    {
                        "error": "Publication step limit reached; inspect the saved intent",
                        "external_execution": "UNKNOWN_OR_NOT_DISPATCHED",
                    }
                ),
                now(),
            ),
        )
        db.execute(
            "UPDATE creative_batches SET state='BLOCKED_HOLD',updated=? WHERE state='ACTIVE' AND EXISTS (SELECT 1 FROM creative_batch_variants v JOIN jobs j ON j.id=v.job_id WHERE v.app_id=creative_batches.app_id AND v.batch_id=creative_batches.id AND j.status='RUNNING' AND j.lease<?)",
            (now(), time.time()),
        )
        db.execute(
            "UPDATE creative_batch_variants SET native_state='STOP_PENDING' WHERE job_id IN (SELECT id FROM jobs WHERE status='RUNNING') AND EXISTS (SELECT 1 FROM creative_batches b WHERE b.app_id=creative_batch_variants.app_id AND b.id=creative_batch_variants.batch_id AND b.state='BLOCKED_HOLD')"
        )
        db.execute(
            "UPDATE creative_batch_variants SET native_state='CANCELLED' WHERE job_id IN (SELECT id FROM jobs WHERE status='QUEUED') AND EXISTS (SELECT 1 FROM creative_batches b WHERE b.app_id=creative_batch_variants.app_id AND b.id=creative_batch_variants.batch_id AND b.state='BLOCKED_HOLD')"
        )
        db.execute(
            "UPDATE jobs SET status='BLOCKED',result=?,updated=? WHERE action='render' AND status='RUNNING' AND lease<? AND EXISTS (SELECT 1 FROM creative_batch_variants v JOIN creative_batches b ON b.app_id=v.app_id AND b.id=v.batch_id WHERE v.job_id=jobs.id AND b.state='BLOCKED_HOLD')",
            (
                canonical(
                    {
                        "error": "Render lease expired; inspect the retained batch hold before recovery",
                        "external_execution": "UNKNOWN",
                    }
                ),
                now(),
                time.time(),
            ),
        )
        db.execute(
            "UPDATE jobs SET status='CANCELLED',updated=? WHERE action='render' AND status='QUEUED' AND EXISTS (SELECT 1 FROM creative_batch_variants v JOIN creative_batches b ON b.app_id=v.app_id AND b.id=v.batch_id WHERE v.job_id=jobs.id AND b.state='BLOCKED_HOLD')",
            (now(),),
        )
        db.execute(
            "UPDATE jobs SET status='FAILED',result=?,updated=? WHERE status='RUNNING' AND lease<? AND attempts>=3 AND action!='social_publication'",
            (canonical({"error": "Recovery attempt limit reached; review the job before retry"}), now(), time.time()),
        )
        candidates = db.execute(
            "SELECT * FROM jobs WHERE (status='QUEUED' OR (status='RUNNING' AND lease<? AND action NOT IN ('campaign_post','campaign_ad','campaign_monitor','social_publication'))) AND ((action='social_publication' AND attempts<1000) OR (action!='social_publication' AND attempts<3)) ORDER BY created",
            (time.time(),),
        )
        row = None
        for candidate in candidates:
            if candidate["action"] == "social_publication":
                from .publication_schedule import ready_job

                if not ready_job(db, candidate):
                    continue
            batch = db.execute(
                "SELECT b.* FROM creative_batches b JOIN creative_batch_variants v ON v.app_id=b.app_id AND v.batch_id=b.id WHERE v.app_id=? AND v.job_id=?",
                (candidate["app_id"], candidate["id"]),
            ).fetchone()
            if batch:
                from .agent_grants import batch_authority_pending
                from .creative_batch_authority import bound_plan

                try:
                    pending = batch_authority_pending(db, bound_plan(batch)["authority"])
                except (Invalid, ValueError, TypeError, KeyError):
                    pending = False
                if pending:
                    continue
            row = candidate
            break
        if not row:
            return None
        db.execute(
            "UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease=?,updated=? WHERE id=?",
            (time.time() + 60, now(), row["id"]),
        )
        claimed = json_job(row)
        claimed["attempts"] += 1
        return claimed


def process(store, job, stop=None):
    """Prepare local packets or perform a configured read-only provider request."""
    if job["action"] in (
        "campaign_post",
        "campaign_ad",
        "campaign_monitor",
        "campaign_owner_report",
        "agent_run",
        "social_publication",
    ):
        return process_special(store, job, stop)
    if job["action"] in ("drive_import", "hypit_render", "edit_render", "render"):
        return process_media(store, job, stop)
    app = store.app(job["app_id"])
    records = store.records(app["id"])
    if job["action"] == "experiment":
        return Experiments(store).evaluate(app["id"], job["data"]["experiment_id"], scheduled=job["data"])
    if job["action"] in ("resolution", "experiment_tracking"):
        return process_evidence_job(store, job)
    if job["action"] == "pipeline":
        from .connection_setup import Connections
        from .subscription_readiness import readiness

        catalog = readiness(app, records, jobs(store, app["id"]), Connections(store).statuses(app["id"]))
        from .release_readiness import readiness as release_readiness

        release = release_readiness(app, records, jobs(store, app["id"]), Connections(store).statuses(app["id"]))
        from .workflow_telemetry import emit

        reports = Ledger(store.path).reports(app["id"])
        result = execute(
            app,
            records,
            job["data"].get("stage", 0),
            reports,
            catalog,
            release,
            progress=lambda code, stage: emit(store, job, code, stage),
        )
        if "goal_packet" in job["data"]:
            from .automatic_preparation import saved_goal

            result = saved_goal(result, job["data"], app, records, reports, catalog, release)
        return result
    binding = current_connection(store, app["id"], job["data"])["data"]
    if "analytics_schedule_id" in job["data"]:
        from .apple_metrics_schedule import check_scheduled

        check_scheduled(store, job)
    from .credential_vault import namespace

    binding = {**binding, "_vault_namespace": namespace(store.path)}
    if "options" in job["data"]:
        if job["data"]["options"].get("operation") == "subscription_catalog":
            from .subscription_readiness import validate_catalog_scope

            validate_catalog_scope(app, binding)
        result = read_report(
            binding,
            app["id"],
            job["data"]["options"],
            connection_id=job["data"].get("connection_id"),
            connection_version=job["data"].get("connection_version"),
        )
    else:
        result = sync(binding, app["id"])
    current_connection(store, app["id"], job["data"])
    if "analytics_schedule_id" in job["data"]:
        from .apple_metrics_schedule import check_scheduled

        check_scheduled(store, job)
    return result


def process_special(store, job, stop):
    """Dispatch scoped special work without widening the generic queue API."""
    if job["action"] == "social_publication":
        from .publication_execution import process_job

        return process_job(store, job)
    if job["action"] == "campaign_owner_report":
        from .campaign_owner_reports import execute

        return execute(store, job)
    if job["action"] == "campaign_monitor":
        from .campaign_monitor import execute

        return execute(store, job)
    if job["action"] in ("campaign_post", "campaign_ad"):
        from .campaign_schedule import execute

        return execute(store, job)
    from .agent_tasks import execute

    return execute(store, job, stop)


def _persist_prepared_apple_metrics(db, store, job, prepared):
    """Commit local partitions only with the still-leased job completion."""
    db.execute("BEGIN IMMEDIATE")
    current = db.execute(
        "SELECT action,data,status,attempts,lease FROM jobs WHERE id=? AND app_id=?", (job["id"], job["app_id"])
    ).fetchone()
    if (
        current is None
        or current["action"] != "sync"
        or current["status"] != "RUNNING"
        or current["attempts"] != job["attempts"]
        or current["lease"] < time.time()
        or json.loads(current["data"]) != job["data"]
    ):
        return None, None
    try:
        if "analytics_schedule_id" in job["data"]:
            from .apple_metrics_schedule import check_scheduled_db

            check_scheduled_db(db, job)
        identity = prepared.identity
        from .apple_analytics import DOWNLOADS

        options = job["data"].get("options", {})
        if (
            identity["app_id"] != job["app_id"]
            or identity["report_id"] != options.get("report_id")
            or identity["report_family"] != options.get("report_family", DOWNLOADS)
            or identity["connection_id"] != job["data"].get("connection_id")
            or identity["connection_version"] != job["data"].get("connection_version")
        ):
            raise Invalid("Apple analytics result no longer matches the leased app connection")
        connection = db.execute(
            "SELECT version,data FROM records WHERE app_id=? AND id=? AND kind=?",
            (job["app_id"], identity["connection_id"], "connection"),
        ).fetchone()
        if connection is None or connection["version"] != identity["connection_version"]:
            raise Invalid("Apple analytics connection changed before persistence")
        binding = json.loads(connection["data"])
        if (
            digest(binding) != prepared.connection_hash
            or binding.get("provider") != "app_store"
            or str(binding.get("store_app_id")) != identity["store_app_id"]
        ):
            raise Invalid("Apple analytics source changed before persistence")
        app_row = db.execute("SELECT id,data,version FROM apps WHERE id=?", (job["app_id"],)).fetchone()
        if app_row is None:
            raise Invalid("Apple analytics app was removed before persistence")
        app = dict(app_row)
        app["data"] = json.loads(app["data"])
        if "manifest_version" in job["data"] and job["data"]["manifest_version"] != app["version"]:
            raise Invalid("Apple analytics app changed before persistence")
        if "agent_policy_sha256" in job["data"]:
            from .marketing_agent_manifest import authorize_read

            authorize_read(app, binding, job["data"])

        from .apple_metrics_store import _reconcile

        db.execute("SAVEPOINT apple_metrics_job")
        try:
            statuses = [_reconcile(db, item["partition"], item["instance"]) for item in prepared.partitions]
            db.execute("RELEASE SAVEPOINT apple_metrics_job")
        except BaseException:
            db.execute("ROLLBACK TO SAVEPOINT apple_metrics_job")
            db.execute("RELEASE SAVEPOINT apple_metrics_job")
            raise
        return prepared.summary(statuses), "SUCCEEDED"
    except Invalid as exc:
        return dict(
            error=str(exc),
            next_action="Refresh the report selection or connection, then retry the read",
            external_execution="READ_COMPLETED_NO_METRIC_PARTITIONS_WRITTEN",
        ), "BLOCKED"
    except Exception:  # noqa: BLE001 - retain a blocked result when persistence cannot be confirmed
        return dict(
            error="Apple analytics observations could not be saved.",
            next_action="Review local storage and the worker status before retrying",
            external_execution="READ_COMPLETED_NO_METRIC_PARTITIONS_WRITTEN",
        ), "BLOCKED"


def process_media(store, job, stop):
    """Keep local media worker dispatch explicit without widening generic queue authority."""
    from .creative_rendering import Renders
    from .drive_import_jobs import Imports
    from .hypit_jobs import HypitRenders
    from .video_edit_jobs import EditRenders

    handlers = {"drive_import": Imports, "hypit_render": HypitRenders, "edit_render": EditRenders, "render": Renders}
    return handlers[job["action"]](store).execute(job, stop)


def process_evidence_job(store, job):
    """Keep exact-approved tracking and resolution dispatch outside generic provider reads."""
    if job["action"] == "experiment_tracking":
        from .experiment_tracking import Tracking

        return Tracking(store).execute(job)
    from .resolution_tools import execute as resolve
    from .sequence_jobs import callback

    on_job = callback(store, job)
    return (
        resolve(store, job["app_id"], job["data"], on_job)
        if on_job is not None
        else resolve(store, job["app_id"], job["data"])
    )


def current_connection(store, app_id, data):
    """Prevent queued or in-flight reads from accepting a rotated connection."""
    if "manifest_version" in data and store.app(app_id)["version"] != data["manifest_version"]:
        raise Invalid("App changed after collection was prepared; refresh campaign inputs")
    record = next(
        (r for r in store.records(app_id) if r["id"] == data.get("connection_id") and r["kind"] == "connection"), None
    )
    if (
        record is None
        or type(data.get("connection_version")) is not int
        or record["version"] != data["connection_version"]
    ):
        raise Invalid("Connection changed or this older run lacks its version; reopen the report and rerun")
    if record["data"].get("provider") == "google_play":
        from .play_contract import require_target

        if type(data.get("manifest_version")) is not int:
            raise Invalid("Google Play read lacks its approved app version; reopen the read")
        require_target(store.app(app_id), record["data"])
    if "agent_policy_sha256" in data:
        from .marketing_agent_manifest import authorize_read

        authorize_read(store.app(app_id), record["data"], data)
    return record


def failed_result(job, error):
    """Only already-permitted transient source reads get the existing bounded retry."""
    if job["action"] == "agent_run":
        from .agent_tasks import ApprovalContextChanged

        if isinstance(error, ApprovalContextChanged):
            return (
                dict(
                    error=str(error),
                    next_action="Review the changed task or approval; the saved connection does not need retesting.",
                    connection_health="UNCHANGED",
                    external_execution="INFERENCE_RESULT_NOT_ACCEPTED",
                ),
                "BLOCKED",
                0,
            )
    if job["action"] in ("campaign_post", "campaign_ad", "campaign_monitor", "drive_import", "social_publication"):
        return failed_special(job)
    if job["action"] == "sync" and "analytics_schedule_id" in job["data"]:
        if transient_read_error(error) and job["attempts"] < 3:
            delay = 5 * job["attempts"]
            return (
                dict(
                    status="RETRY_WAIT",
                    summary="Transient scheduled Apple read failure; bounded retry queued",
                    attempt=job["attempts"],
                    retry_in_seconds=delay,
                    next_action="The worker will retry this same owner-enabled read within its three-attempt limit",
                    external_execution="READ_RETRY_PENDING",
                ),
                "RUNNING",
                delay,
            )
        return (
            dict(
                error="Scheduled Apple analytics read failed; review the connection and latest job result",
                next_action="Open the Apple analytics schedule, review the failure, and reconnect or resume explicitly",
                external_execution="READ_ATTEMPT_MAY_HAVE_OCCURRED",
            ),
            "BLOCKED",
            0,
        )
    result = {
        "error": str(error),
        "next_action": "Review inputs or connection, then create a new run",
        "external_execution": "NOT_RUN",
    }
    if job["action"] != "sync" or "agent_policy_sha256" not in job["data"] or job["attempts"] >= 3:
        return result, "BLOCKED", 0
    if not transient_read_error(error):
        return result, "BLOCKED", 0
    delay = 5 * job["attempts"]
    return (
        dict(
            status="RETRY_WAIT",
            summary="Transient provider read failure; safe retry scheduled",
            attempt=job["attempts"],
            retry_in_seconds=delay,
            next_action="Worker will retry this same approved read within its three-attempt limit",
            external_execution="READ_RETRY_PENDING",
        ),
        "RUNNING",
        delay,
    )


def failed_special(job):
    """Failures of special jobs never inherit generic retries."""
    if job["action"] == "social_publication":
        return (
            dict(
                error="Publication stopped; reconcile the saved intent before another action.",
                external_execution="UNKNOWN_OR_NOT_DISPATCHED",
            ),
            "BLOCKED",
            0,
        )
    if job["action"] in ("campaign_post", "campaign_ad", "campaign_monitor"):
        return (
            dict(
                error="Scheduled campaign stopped; inspect its saved campaign intent before any retry.",
                next_action="Review the exact intent and provider state.",
                external_execution="UNKNOWN_OR_NOT_DISPATCHED",
            ),
            "BLOCKED",
            0,
        )
    return (
        dict(
            error="Drive import stopped at a source, permission or validation boundary.",
            next_action="Inspect the private Drive import and reconnect, review or retry explicitly.",
            external_execution="READ_ATTEMPT_MAY_HAVE_OCCURRED",
        ),
        "BLOCKED",
        0,
    )


def run_once(store, stop=None):
    """Complete one leased job without overwriting cancellation or hiding failure."""
    from .sequence_jobs import guard_owned
    from .sequence_runtime import advance

    progressed = advance(store)
    job = claim(store)
    if not job:
        return progressed
    retry_delay = 0
    if job["action"] == "render":
        from .media_native import track_children

        tracking = track_children()
    else:
        tracking = nullcontext(None)
    with tracking as children:
        try:
            guard_owned(store, job)
            from .automation_execution import job_execution

            with job_execution(store, job):
                from .workflow_telemetry import emit

                emit(store, job, "STARTED")
                result = process(store, job) if stop is None else process(store, job, stop)
            guard_owned(store, job)
            status = (
                "BLOCKED"
                if job["action"] == "campaign_monitor"
                and isinstance(result, dict)
                and result.get("status") == "BLOCKED"
                else "SUCCEEDED"
            )
        except Exception as exc:  # noqa: BLE001 - worker failures must persist a non-replayed recovery result
            result, status, retry_delay = failed_result(job, exc)
    persist_job_result(store, job, result, status, retry_delay)
    if children is not None and children["active"] == 0 and not children["uncertain"]:
        from .creative_batches import ack_desktop_stop

        ack_desktop_stop(store, job)
    return True


def persist_job_result(store, job, result, status, retry_delay):
    """Commit only the still-owned result and its existing telemetry/hooks."""
    from .publication_execution import PreparedPublicationStep

    with connection(store.path) as db:
        if isinstance(result, PreparedPublicationStep):
            from .publication_schedule import finish_step

            db.execute("BEGIN IMMEDIATE")
            outcome = finish_step(db, store, job, result.result, result.reschedule_at)
            from .workflow_telemetry import append

            append(db, job, "RETRY_WAIT" if outcome["job_status"] == "QUEUED" else outcome["job_status"])
            db.execute(
                "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
                (
                    job["app_id"],
                    "job." + outcome["job_status"].lower(),
                    canonical({"id": job["id"], "action": job["action"], "result_hash": digest(result.result)}),
                    now(),
                ),
            )
            return
        if isinstance(result, PreparedAppleMetrics):
            result, status = _persist_prepared_apple_metrics(db, store, job, result)
            if status is None:
                return
        changed = db.execute(
            "UPDATE jobs SET status=?,result=?,lease=?,updated=? WHERE id=? AND status='RUNNING' AND attempts=?",
            (
                status,
                canonical(result),
                time.time() + retry_delay if retry_delay else 0,
                now(),
                job["id"],
                job["attempts"],
            ),
        ).rowcount
        if changed:
            if job["action"] == "social_publication" and status == "BLOCKED":
                db.execute(
                    "UPDATE publication_schedules SET status='BLOCKED',updated=? WHERE job_id=? AND status='QUEUED'",
                    (now(), job["id"]),
                )
            from .workflow_telemetry import append

            append(db, job, "RETRY_WAIT" if retry_delay else status)
            if "analytics_schedule_id" in job["data"]:
                from .apple_metrics_schedule import complete_job

                complete_job(db, job, result, status)
            if job["action"] == "agent_run":
                from .agent_tasks import complete as agent_complete

                agent_complete(db, job, result, status)
            db.execute(
                "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
                (
                    job["app_id"],
                    "job." + status.lower(),
                    canonical({"id": job["id"], "action": job["action"], "result_hash": digest(result)}),
                    now(),
                ),
            )


def transient_read_error(error):
    """Retry typed transport failures only; never infer permission from error text."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, HTTPError):
            return error.code in (408, 429, 500, 502, 503, 504)
        if isinstance(error, (URLError, TimeoutError, ConnectionError)):
            return True
        error = error.__cause__
    return False


class Runner:
    def __init__(self, store):
        self.store = store
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="growth-worker")
        self.supervision = Supervision()

    @property
    def health(self):
        return self.supervision.snapshot()

    def retry_failed(self):
        """Request recovery without re-enabling app policy or replaying failed jobs."""
        self.supervision.retry.set()
        return {"status": "RETRY_REQUESTED", "scope": "SHARED_LOCAL_WORKER_FAILED_COMPONENTS_ONLY"}

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
        self.supervision.attempt("experiments", lambda: Schedules(self.store).tick(), 1)
        from .creative_batches import Batch

        self.supervision.attempt("creative_batches", lambda: Batch(self.store).tick(), 1)
        self.supervision.attempt("analytics", lambda: Insights(self.store).tick(), 1)
        from .apple_metrics_schedule import AppleMetricsSchedules

        self.supervision.attempt("apple_metrics", lambda: AppleMetricsSchedules(self.store).tick(), 1)
        from .campaign_schedule import tick as campaign_tick

        self.supervision.attempt("campaign_schedule", lambda: campaign_tick(self.store), 1)
        from .campaign_monitor import tick as monitor_tick

        self.supervision.attempt("campaign_monitor", lambda: monitor_tick(self.store), 1)
        from .campaign_owner_reports import tick as owner_reports_tick

        self.supervision.attempt("owner_reports", lambda: owner_reports_tick(self.store), 1)
        self.supervision.attempt("followup", lambda: Followup(self.store).tick(), 1)
        from .social_renewal import Renewal

        self.supervision.attempt("social", lambda: Renewal(self.store).tick(), 60)
        worked = self.supervision.attempt("queue", lambda: run_once(self.store, self.stop_event))
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
