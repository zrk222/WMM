"""Durable opt-in local analysis; provider execution is outside this scheduler."""
from datetime import timedelta
from .common import Invalid,canonical,digest,iso_time,now,safe_data,uid
from .db import connection
from .experiments import lookup

STATUSES={"ENABLED","PAUSED","BLOCKED","RESTORED_PAUSED","CANCELLED"}


def configuration(body):
    """Require explicit enable, bounded cadence and optimistic configuration version."""
    safe_data(body)
    if set(body)!={"enabled","interval_hours","version"} or type(body["enabled"]) is not bool:raise Invalid("Choose enabled, interval and current version")
    if type(body["interval_hours"]) is not int or not 1<=body["interval_hours"]<=168:raise Invalid("Choose an interval from 1 to 168 whole hours")
    if body["version"] is not None and type(body["version"]) is not int:raise Invalid("Invalid schedule version")
    return body


def schedule_audit(db,app_id,experiment_id,operation,detail):
    """Retain public schedule evidence separately from experiment definitions."""
    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,"schedule."+operation,canonical(dict(detail,experiment_id=experiment_id)),now()))


def pause_queued(db,row):
    """Cancel only this schedule's queued job; running assessment may finish."""
    if not row or not row["last_job"]:return
    db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=? AND status='QUEUED'",(now(),row["app_id"],row["last_job"]))


class Schedules:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Return persistent scoped public settings and exact latest job status."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM experiment_schedules WHERE app_id=? ORDER BY experiment_id",(app_id,))]
            for row in rows:
                row["enabled"]=bool(row["enabled"])
                job=db.execute("SELECT status FROM jobs WHERE app_id=? AND id=?",(app_id,row["last_job"])).fetchone()
                row["last_job_status"]=job["status"] if job else None
            return rows

    def save(self,app_id,experiment_id,body):
        """Explicitly enable/resume or pause an observed test without external effects."""
        self.store.app(app_id);body=configuration(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            experiment=lookup(db,app_id,experiment_id)
            if experiment["state"] in ("PLANNED","CANCELLED"):raise Invalid("Record exposure first; cancelled tests cannot be scheduled")
            old=db.execute("SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?",(app_id,experiment_id)).fetchone()
            expected=old["version"] if old else None
            if body["version"]!=expected:raise Invalid("Schedule changed; reload before saving")
            pause_queued(db,old)
            stamp=now();due=max(iso_time(stamp),iso_time(experiment["data"]["analysis_at"])).isoformat()
            status="ENABLED" if body["enabled"] else "PAUSED";version=(expected or 0)+1
            last_job=existing_job(db,old)
            db.execute("INSERT OR REPLACE INTO experiment_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?)",(app_id,experiment_id,int(body["enabled"]),body["interval_hours"],version,due,last_job,last_job,0,status,stamp))
            schedule_audit(db,app_id,experiment_id,"saved",{"enabled":body["enabled"],"version":version,"next_due":due})
        return next(s for s in self.list(app_id) if s["experiment_id"]==experiment_id)

    def tick(self):
        """Reconcile and atomically dispatch at most one pending run per active test."""
        count=0
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            rows=db.execute("SELECT * FROM experiment_schedules WHERE enabled=1 ORDER BY next_due LIMIT 100").fetchall()
            for row in rows:
                current=lookup(db,row["app_id"],row["experiment_id"])
                if current["state"]=="CANCELLED":
                    disable(db,row,"CANCELLED");continue
                if not reconcile(db,row):continue
                fresh=db.execute("SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?",(row["app_id"],row["experiment_id"])).fetchone()
                if iso_time(fresh["next_due"])<=iso_time(now()):
                    dispatch(db,fresh,current);count+=1
        return count


def disable(db,row,status):
    """Preserve failed receipts while preventing unbounded retry or cancellation loops."""
    pause_queued(db,row)
    db.execute("UPDATE experiment_schedules SET enabled=0,status=?,updated=? WHERE app_id=? AND experiment_id=?",(status,now(),row["app_id"],row["experiment_id"]))
    schedule_audit(db,row["app_id"],row["experiment_id"],"disabled",{"status":status})


def existing_job(db,row):
    """Explicit resume retires a missing receipt without pretending it completed."""
    if not row or not row["last_job"]:return None
    job=db.execute("SELECT id FROM jobs WHERE app_id=? AND id=?",(row["app_id"],row["last_job"])).fetchone()
    return job["id"] if job else None


def reconcile(db,row):
    """Apply each terminal result once and disable after three operational failures."""
    if not row["last_job"]:return True
    job=db.execute("SELECT status FROM jobs WHERE app_id=? AND id=?",(row["app_id"],row["last_job"])).fetchone()
    if not job:disable(db,row,"BLOCKED");return False
    if job["status"] in ("QUEUED","RUNNING"):return False
    if row["reconciled_job"]==row["last_job"]:return True
    failures=0 if job["status"]=="SUCCEEDED" else row["failures"]+1
    db.execute("UPDATE experiment_schedules SET failures=?,reconciled_job=?,updated=? WHERE app_id=? AND experiment_id=?",(failures,row["last_job"],now(),row["app_id"],row["experiment_id"]))
    schedule_audit(db,row["app_id"],row["experiment_id"],"reconciled",{"job_id":row["last_job"],"status":job["status"],"failures":failures})
    if job["status"]=="CANCELLED":disable(db,row,"PAUSED");return False
    if failures>=3:disable(db,row,"BLOCKED");return False
    return True


def dispatch(db,row,experiment):
    """Commit one leased-job input and future due time in the same transaction."""
    data={"experiment_id":row["experiment_id"],"schedule_version":row["version"],"due":row["next_due"],"source_hash":experiment["hash"]}
    request_key="schedule-"+digest(dict(data,app_id=row["app_id"]))
    job_id=uid();stamp=now()
    db.execute("INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",(job_id,row["app_id"],"experiment",canonical(data),"QUEUED",stamp,stamp,request_key))
    saved=db.execute("SELECT id FROM jobs WHERE app_id=? AND request_key=?",(row["app_id"],request_key)).fetchone()[0]
    next_due=(iso_time(stamp)+timedelta(hours=row["interval_hours"])).isoformat()
    db.execute("UPDATE experiment_schedules SET last_job=?,next_due=?,updated=? WHERE app_id=? AND experiment_id=?",(saved,next_due,stamp,row["app_id"],row["experiment_id"]))
    schedule_audit(db,row["app_id"],row["experiment_id"],"queued",{"job_id":saved,"request_key":request_key})


def check_scheduled(db,current,data):
    """Validate current schedule authorization inside the actual assessment transaction."""
    if set(data)!={"experiment_id","schedule_version","due","source_hash"}:raise Invalid("Invalid scheduled analysis input")
    row=db.execute("SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?",(current["app_id"],current["id"])).fetchone()
    if not row or not row["enabled"] or row["version"]!=data["schedule_version"]:raise Invalid("Schedule paused or replaced; reload current configuration")
    if current["hash"]!=data["source_hash"] or current["id"]!=data["experiment_id"]:raise Invalid("Scheduled experiment source changed")
    if iso_time(data["due"])>iso_time(now()):raise Invalid("Scheduled analysis is not due")


def export_schedules(store,app_id):
    """Export settings and recovery state without claiming transferable job authority."""
    return [{k:v for k,v in row.items() if k!="last_job_status"} for row in Schedules(store).list(app_id)]


def restore_schedules(db,app_id,items):
    """Restore disabled settings: exported job IDs cannot authorize another workstation."""
    if items is None:return
    if not isinstance(items,list) or len(items)>1000:raise Invalid("Invalid schedule collection")
    seen=set()
    for row in items:
        validate_restored_schedule(db,app_id,row)
        if row["experiment_id"] in seen:raise Invalid("Duplicate restored schedule")
        seen.add(row["experiment_id"])
        db.execute("INSERT INTO experiment_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?)",(app_id,row["experiment_id"],0,row["interval_hours"],row["version"],row["next_due"],None,None,0,"RESTORED_PAUSED",now()))


def validate_restored_schedule(db,app_id,row):
    """Require exact scoped setting schema, integer limits and valid history references."""
    fields={"app_id","experiment_id","enabled","interval_hours","version","next_due","last_job","reconciled_job","failures","status","updated"}
    if not isinstance(row,dict) or set(row)!=fields or row["app_id"]!=app_id:raise Invalid("Restored schedule scope or schema mismatch")
    configuration({k:row[k] for k in ("enabled","interval_hours","version")})
    restored_limits(row)
    iso_time(row["next_due"]);iso_time(row["updated"])
    experiment=lookup(db,app_id,row["experiment_id"])
    if experiment["state"]=="PLANNED" or row["enabled"] and experiment["state"]=="CANCELLED":raise Invalid("Restored schedule conflicts with experiment state")


def restored_limits(row):
    """Reject incoherent enable/status combinations and invalid recovery bounds."""
    if row["version"] is None or row["version"]<1 or type(row["failures"]) is not int or not 0<=row["failures"]<=3:raise Invalid("Invalid restored schedule version or failures")
    if row["status"] not in STATUSES or bool(row["enabled"])!=(row["status"]=="ENABLED"):raise Invalid("Invalid restored schedule status")
