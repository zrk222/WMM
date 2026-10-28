"""Actual isolated durable queue and fixed-component fault containment."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from mission_control.automation_health import COMPONENTS, Supervision
from mission_control.store import Store
from mission_control.worker import Runner, enqueue, jobs

TICKS = ("Schedules", "Insights", "AppleMetricsSchedules", "Followup")


def tick_target(name):
    if name == "AppleMetricsSchedules":
        return "mission_control.apple_metrics_schedule.AppleMetricsSchedules.tick"
    return "mission_control.worker." + name + ".tick"


class AutomationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.sqlite")
        self.runner = Runner(self.store)

    def test_each_failed_schedule_keeps_actual_queue_and_other_schedules_running(self):
        for failed in TICKS:
            with self.subTest(failed=failed), ExitStack() as stack:
                calls = {}
                for name in TICKS:
                    calls[name] = stack.enter_context(patch(tick_target(name),
                        side_effect=OSError("api_key=secret") if name == failed else None, return_value=0))
                enqueue(self.store,"sample-one","pipeline",{"stage":0},failed)
                runner = Runner(self.store)
                self.assertTrue(runner.poll())
                self.assertTrue(all(c.call_count == 1 for c in calls.values()))
                self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"SUCCEEDED")
                health=runner.health
                self.assertEqual(health["status"],"RECOVERING")
                self.assertIsNone(health["last_success"])
                self.assertNotIn("secret",json.dumps(health))
                self.assertEqual(health["components"]["queue"]["status"],"RUNNING")
                apple_status = health["components"]["apple_metrics"]["status"]
                self.assertEqual(apple_status,"RECOVERING" if failed == "AppleMetricsSchedules" else "RUNNING")

    def test_three_attempts_backoff_pause_and_explicit_retry(self):
        supervisor=Supervision();clock=[100.0]
        failing=Mock(side_effect=OSError("secret"))
        with patch("mission_control.automation_health.time.monotonic",side_effect=lambda:clock[0]):
            supervisor.attempt("analytics",failing)
            clock[0]=100.99;supervisor.attempt("analytics",failing)
            self.assertEqual(failing.call_count,1)
            clock[0]=101;supervisor.attempt("analytics",failing)
            clock[0]=102.99;supervisor.attempt("analytics",failing)
            self.assertEqual(failing.call_count,2)
            clock[0]=103;supervisor.attempt("analytics",failing)
            clock[0]=10000;supervisor.attempt("analytics",failing)
            self.assertEqual(failing.call_count,3)
            self.assertEqual(supervisor.snapshot()["components"]["analytics"]["status"],"PAUSED")
            supervisor.retry.set();supervisor.begin()
            self.assertEqual(supervisor.snapshot()["components"]["analytics"]["failures"],0)
            supervisor.attempt("analytics",lambda:0)
            self.assertEqual(supervisor.snapshot()["components"]["analytics"]["status"],"RUNNING")

    def test_success_does_not_mask_failure_and_snapshots_are_detached(self):
        s=Supervision()
        for name in COMPONENTS:s.attempt(name,lambda:0)
        s.finish();first=s.snapshot();self.assertEqual(first["status"],"RUNNING")
        with patch("mission_control.automation_health.now",return_value="later"):
            s.attempt("analytics",Mock(side_effect=OSError("private")))
            s.attempt("queue",lambda:1);s.finish()
        health=s.snapshot();self.assertEqual(health["status"],"RECOVERING")
        self.assertEqual(health["last_success"],first["last_success"])
        self.assertEqual(health["components"]["queue"]["last_success"],"later")
        health["components"]["analytics"]["failures"]=999
        self.assertEqual(s.snapshot()["components"]["analytics"]["failures"],1)
        self.assertNotIn("next_due",json.dumps(s.snapshot()))

    def test_queue_failure_does_not_block_schedules_or_repeat_before_due(self):
        with ExitStack() as stack:
            calls=[stack.enter_context(patch(tick_target(n),return_value=0)) for n in TICKS]
            queue=stack.enter_context(patch("mission_control.worker.run_once",side_effect=OSError("private")))
            self.assertFalse(self.runner.poll());self.assertFalse(self.runner.poll())
            self.assertEqual(queue.call_count,1)
            self.assertTrue(all(c.call_count==1 for c in calls))
            self.assertEqual(self.runner.health["components"]["queue"]["failures"],1)

    def test_retry_does_not_change_durable_configuration_or_replay_failed_jobs(self):
        enqueue(self.store,"sample-one","pipeline",{"stage":0},"one")
        with patch("mission_control.worker.process",side_effect=OSError("no packet")):
            self.runner.poll()
        self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"BLOCKED")
        before=self.store.export("sample-one")["payload"]
        result=self.runner.retry_failed();self.assertEqual(result["status"],"RETRY_REQUESTED")
        self.assertFalse(self.runner.poll())
        self.assertEqual(self.store.export("sample-one")["payload"],before)
        self.assertEqual(jobs(self.store,"sample-one")[0]["attempts"],1)

    def test_retry_is_consumed_between_attempts_and_preserves_healthy_state(self):
        s=Supervision();entered=threading.Event();release=threading.Event()
        def failing():entered.set();release.wait(3);raise OSError("private")
        s.attempt("queue",lambda:0);healthy=s.snapshot()["components"]["queue"]
        thread=threading.Thread(target=lambda:s.attempt("analytics",failing));thread.start()
        try:
            self.assertTrue(entered.wait(3));s.retry.set()
            self.assertEqual(s.snapshot()["components"]["analytics"]["failures"],0)
        finally:release.set();thread.join(3)
        self.assertEqual(s.snapshot()["components"]["analytics"]["failures"],1)
        s.begin();self.assertFalse(s.retry.is_set())
        self.assertEqual(s.snapshot()["components"]["analytics"]["failures"],0)
        self.assertEqual(s.snapshot()["components"]["queue"]["last_success"],healthy["last_success"])

    def test_real_background_queue_survives_failed_schedule_and_stops(self):
        enqueue(self.store,"sample-one","pipeline",{"stage":0},"background")
        with patch("mission_control.worker.Schedules.tick",side_effect=OSError("private")):
            self.runner.start()
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline and jobs(self.store,"sample-one")[0]["status"]!="SUCCEEDED":time.sleep(.02)
                self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"SUCCEEDED")
                self.assertEqual(self.runner.health["status"],"RECOVERING")
            finally:self.runner.stop()
        self.assertEqual(self.runner.health["status"],"STOPPED")
        self.assertFalse(self.runner.thread.is_alive());self.assertFalse(self.runner.poll())

    def test_process_cancellation_is_not_swallowed(self):
        with self.assertRaises(KeyboardInterrupt):
            self.runner.supervision.attempt("queue",Mock(side_effect=KeyboardInterrupt))

    def test_restart_preserves_durable_work_and_does_not_import_health_authority(self):
        enqueue(self.store,"sample-two","pipeline",{"stage":0},"restart")
        before=self.store.export("sample-two")["payload"]
        with patch("mission_control.worker.run_once",side_effect=OSError("private")):
            self.runner.poll()
        restarted=Runner(Store(self.store.path))
        self.assertEqual(restarted.health["status"],"STARTING")
        self.assertEqual(self.store.export("sample-two")["payload"],before)
        self.assertTrue(restarted.poll())
        self.assertEqual(jobs(self.store,"sample-two")[0]["status"],"SUCCEEDED")

    def test_bounded_readonly_idle_poll_performance(self):
        before=self.store.export("sample-one")["payload"];start=time.monotonic()
        for _ in range(100):self.assertFalse(self.runner.poll())
        self.assertLess(time.monotonic()-start,5)
        self.assertEqual(self.store.export("sample-one")["payload"],before)


if __name__=="__main__":unittest.main()
