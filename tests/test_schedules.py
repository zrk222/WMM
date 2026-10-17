"""Durable local schedule execution and bounded recovery with real SQLite workers."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.experiments import Experiments
from mission_control.experiment_schedules import (Schedules,configuration,check_scheduled,export_schedules,validate_restored_schedule,
                                               pause_queued,disable,existing_job,reconcile,restore_schedules,restored_limits)
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import Runner,run_once,jobs,claim,process
from tests.test_experiments import prepared,observations,REGISTER,EXPOSE,ANALYZE,LATER


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"source/state.sqlite")
        self.service=Service(self.store);self.experiments=Experiments(self.store);self.schedules=Schedules(self.store)
        plan=prepared(self.store)
        with patch("mission_control.experiments.now",return_value=REGISTER):self.e=self.experiments.create("sample-one",plan)
        with patch("mission_control.experiments.now",return_value=EXPOSE):self.experiments.act("sample-one",self.e["id"],dict(operation="observe",version=1,source="Synthetic receipt",observed_at=EXPOSE))
        for arm in ("control","treatment"):
            self.service.events("sample-one",{"cohort_id":plan[arm]["cohort_id"],"events":observations(arm,activations=10 if arm=="control" else 16)})

    def tearDown(self):self.tmp.cleanup()

    def setting(self):return self.schedules.list("sample-one")[0]

    def save(self,enabled=True,version=None,stamp=ANALYZE):
        with patch("mission_control.experiment_schedules.now",return_value=stamp):return self.schedules.save("sample-one",self.e["id"],dict(enabled=enabled,interval_hours=24,version=version))

    def tick(self,stamp=ANALYZE):
        with patch("mission_control.experiment_schedules.now",return_value=stamp):return self.schedules.tick()

    def execute(self,stamp=ANALYZE):
        with patch("mission_control.experiment_schedules.now",return_value=stamp),patch("mission_control.experiments.now",return_value=stamp):return run_once(self.store)

    def test_configuration_scope_and_fixed_due(self):
        for body in ({},dict(enabled="yes",interval_hours=24,version=None),dict(enabled=True,interval_hours=0,version=None),dict(enabled=True,interval_hours=169,version=None),dict(enabled=True,interval_hours=True,version=None),dict(enabled=True,interval_hours=24,version=True)):
            with self.subTest(body=body),self.assertRaises(Invalid):configuration(body)
        with self.assertRaises(Invalid):self.schedules.save("sample-two",self.e["id"],dict(enabled=True,interval_hours=24,version=None))
        self.assertEqual(self.schedules.list("sample-two"),[])
        s=self.save(stamp=EXPOSE);self.assertEqual(s["next_due"],ANALYZE)
        self.assertEqual(self.tick(EXPOSE),0);self.assertEqual(jobs(self.store,"sample-one"),[])
        with self.assertRaises(Invalid):self.save(version=None)
        self.assertEqual(self.save(False,s["version"])["status"],"PAUSED")

    def test_atomic_dispatch_restart_and_idempotent_assessment(self):
        self.save();self.assertEqual(self.tick(),1);self.assertEqual(self.tick(),0)
        pending=jobs(self.store,"sample-one");self.assertEqual(len(pending),1);self.assertEqual(pending[0]["action"],"experiment")
        restarted=Store(self.store.path);self.assertEqual(Schedules(restarted).list("sample-one")[0]["last_job"],pending[0]["id"])
        self.assertTrue(self.execute());result=jobs(self.store,"sample-one")[0]
        self.assertEqual(result["status"],"SUCCEEDED");self.assertEqual(result["result"]["result"]["status"],"EVALUATED")
        self.assertEqual(self.tick(),0);self.assertEqual(self.setting()["failures"],0)
        self.assertEqual(self.tick("2026-10-03T00:00:00+00:00"),1);self.execute("2026-10-03T00:00:00+00:00")
        self.assertFalse(jobs(self.store,"sample-one")[0]["result"]["new_assessment"])
        self.assertEqual(len(self.experiments.list("sample-one")[0]["assessments"]),1)

    def test_dispatch_transaction_rolls_back_on_failed_audit(self):
        self.save();before=self.setting()
        with patch("mission_control.experiment_schedules.schedule_audit",side_effect=OSError("synthetic disk failure")),self.assertRaises(OSError):self.tick()
        self.assertEqual(jobs(self.store,"sample-one"),[]);self.assertEqual(self.setting(),before)
        self.assertEqual(self.tick(),1)

    def test_pause_cancels_queue_and_rejects_replaced_running_input(self):
        self.save();self.tick();job=jobs(self.store,"sample-one")[0]
        self.save(False,version=1)
        self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"CANCELLED");self.assertFalse(self.execute())
        self.save(True,version=2);self.tick();running=claim(self.store)
        self.save(False,version=3)
        with patch("mission_control.experiment_schedules.now",return_value=ANALYZE),self.assertRaisesRegex(Invalid,"paused or replaced"):process(self.store,running)
        self.assertEqual(self.tick(LATER),0)
        self.assertEqual(self.experiments.list("sample-one")[0]["assessments"],[])

    def test_failure_limit_reconcile_once_and_explicit_resume(self):
        self.save()
        for index,day in enumerate(("2026-10-02","2026-10-03","2026-10-04")):
            stamp=day+"T00:00:00+00:00";self.assertEqual(self.tick(stamp),1)
            with patch("mission_control.worker.process",side_effect=Invalid("Synthetic failure")):self.execute(stamp)
            self.tick(stamp);self.tick(stamp)
            self.assertEqual(self.setting()["failures"],index+1)
        s=self.setting();self.assertFalse(s["enabled"]);self.assertEqual(s["status"],"BLOCKED")
        self.assertEqual(self.tick(LATER),0);self.save(True,s["version"],stamp=LATER)
        self.assertEqual(self.setting()["failures"],0);self.tick(LATER);self.execute(LATER);self.tick(LATER)
        self.assertEqual(self.setting()["status"],"ENABLED")

    def test_missing_job_cancelled_job_and_terminal_experiment_stop(self):
        self.save();self.tick();s=self.setting()
        self.service.cancel("sample-one",s["last_job"]);self.tick()
        self.assertEqual(self.setting()["status"],"PAUSED")
        self.save(True,self.setting()["version"]);self.tick()
        with connection(self.store.path) as db:db.execute("DELETE FROM jobs WHERE id=?",(self.setting()["last_job"],))
        self.tick();self.assertEqual(self.setting()["status"],"BLOCKED")
        self.save(True,self.setting()["version"]);self.tick()
        with patch("mission_control.experiments.now",return_value=ANALYZE):self.experiments.act("sample-one",self.e["id"],dict(operation="cancel",version=2,reason="Synthetic stop"))
        self.tick();self.assertEqual(self.setting()["status"],"CANCELLED")
        self.assertFalse(self.setting()["enabled"])

    def test_scheduled_source_and_due_validation(self):
        self.save();self.tick();job=jobs(self.store,"sample-one")[0];current=self.experiments.list("sample-one")[0]
        with connection(self.store.path) as db,patch("mission_control.experiment_schedules.now",return_value=ANALYZE):
            check_scheduled(db,current,job["data"])
            for change in ({"source_hash":"0"*64},{"schedule_version":999},{"due":"2999-01-01T00:00:00+00:00"},{"experiment_id":"other"},{"extra":True}):
                with self.subTest(change=change),self.assertRaises(Invalid):check_scheduled(db,current,dict(job["data"],**change))

    def test_snapshot_disabled_and_tamper_atomic(self):
        self.save();self.tick();self.execute();snapshot=self.store.export("sample-one")
        self.assertEqual(export_schedules(self.store,"sample-one"),snapshot["payload"]["schedules"])
        target=Store(Path(self.tmp.name)/"target/state.sqlite",seed=False);target.restore(snapshot)
        row=Schedules(target).list("sample-one")[0]
        self.assertFalse(row["enabled"]);self.assertEqual(row["status"],"RESTORED_PAUSED");self.assertIsNone(row["last_job"])
        self.assertEqual(Schedules(target).tick(),0)
        for change in ({"app_id":"sample-two"},{"version":0},{"failures":4},{"interval_hours":0},{"status":"SUCCESS"},{"next_due":"yesterday"}):
            bad=copy.deepcopy(snapshot);bad["payload"]["schedules"][0].update(change);bad["sha256"]=digest(bad["payload"])
            other=Store(Path(self.tmp.name)/str(len(list(Path(self.tmp.name).iterdir())))/"state.sqlite",seed=False)
            with self.subTest(change=change),self.assertRaises(Invalid):other.restore(bad)
            self.assertEqual(other.apps(),[])
        with connection(self.store.path) as db:validate_restored_schedule(db,"sample-one",snapshot["payload"]["schedules"][0])

    def test_worker_health_redaction_and_recovery(self):
        runner=Runner(self.store)
        with patch("mission_control.worker.run_once",side_effect=OSError("api_key=private-value")):
            self.assertFalse(runner.poll())
        self.assertEqual(runner.health["status"],"RECOVERING");self.assertNotIn("private-value",json.dumps(runner.health))
        runner.retry_failed()
        self.assertFalse(runner.poll());self.assertEqual(runner.health["status"],"RUNNING")
        self.assertIsNotNone(runner.health["last_success"])

    def test_schedule_helpers_preserve_receipts_and_disable_restore(self):
        self.save();self.tick();row=self.setting()
        with connection(self.store.path) as db:
            self.assertEqual(existing_job(db,row),row["last_job"])
            self.assertFalse(reconcile(db,row));pause_queued(db,row)
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?",(row["last_job"],)).fetchone()[0],"CANCELLED")
            disable(db,row,"PAUSED")
            exported=export_schedules(self.store,"sample-one")
            restored_limits(exported[0]);validate_restored_schedule(db,"sample-one",exported[0])
            restore_schedules(db,"sample-one",None)
            for invalid in ({"enabled":True,"status":"PAUSED"},{"version":0},{"failures":True}):
                with self.assertRaises(Invalid):restored_limits(dict(exported[0],**invalid))

    def test_actual_background_runner_completes_due_job(self):
        self.save(stamp="2026-10-01T00:00:00+00:00")
        runner=Runner(self.store);runner.start()
        try:
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                saved=jobs(self.store,"sample-one")
                if saved and saved[0]["status"]=="SUCCEEDED":break
                time.sleep(.05)
            self.assertEqual(saved[0]["status"],"SUCCEEDED")
            self.assertEqual(runner.health["status"],"RUNNING")
        finally:runner.stop()
        self.assertEqual(runner.health["status"],"STOPPED");self.assertFalse(runner.thread.is_alive())


if __name__=="__main__":unittest.main()
