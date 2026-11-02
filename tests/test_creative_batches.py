"""Finite plan and actual local output inspection in isolated workspaces."""
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.agent_grants import Grants
from mission_control.creative_batch_authority import bound_plan, guard_batch, guard_render
from mission_control.creative_batches import Batch, ack_desktop_stop, inspect_output, plan_data, prepare, public_batch
from mission_control.creative_rendering import Renders, artifact_file, render_request
from mission_control.db import connection
from mission_control.operation_authority import bound_agent, bound_owner, protected
from mission_control.operator_identity import Identities
from mission_control.operation_runtime import execute
from mission_control.review_access import Access
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import claim, enqueue_db, jobs, run_once
from tests.test_creative_rendering import APP, prepared_render
from tests.test_verified_review import OWNER


class CreativeBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite")
        self.brief, self.request = prepared_render(self.store)
        self.expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})
        self.identity = Identities()
        self.session = "synthetic-batch-owner"
        self.identity.sessions[self.session] = dict(user=OWNER, token="fixture-only", expires=time.time()+900)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_is_finite_proof_bound_and_read_only(self):
        other = dict(self.request, shape="LANDSCAPE")
        selection = dict(variants=[self.request, other], max_total_frames=2880, runtime="DESKTOP", expires=self.expires)
        prepared = prepare(self.store, APP, selection)
        plan = prepared["plan"]
        self.assertEqual(plan["total_frames"], 2 * self.brief["data"]["definition"]["duration_seconds"] * 24)
        self.assertEqual(plan["manifest_version"], self.store.app(APP)["version"])
        self.assertEqual(plan["publication"], "NOT_RUN")
        self.assertEqual(jobs(self.store, APP), [])
        for invalid in (dict(selection, variants=[]),
                        dict(selection, variants=[self.request] * 9),
                        dict(selection, variants=[self.request] * 2),
                        dict(selection, variants=[None]),
                        dict(selection, max_total_frames=True),
                        dict(selection, max_total_frames=1),
                        dict(selection, runtime="REMOTE"),
                        dict(selection, expires="2000-01-01T00:00:00+00:00"),
                        dict(selection, variants=[dict(self.request, brief_hash="wrong")])):
            with self.subTest(invalid=invalid), self.assertRaises(Invalid):
                prepare(self.store, APP, invalid)
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], release="changed"), app["version"])
        with self.assertRaises(Invalid):
            prepare(self.store, APP, selection)

    def test_real_output_is_decoded_but_visual_review_remains_unknown(self):
        queued = Renders(self.store).queue(APP, dict(data=self.request, request_key="inspection-fixture"))
        self.assertTrue(run_once(self.store))
        job = next(row for row in jobs(self.store, APP) if row["id"] == queued["id"])
        self.assertEqual(job["status"], "SUCCEEDED", job["result"])
        result = inspect_output(self.store, APP, job["result"]["render_id"])
        self.assertEqual(result["decoded_frames"], 4)
        self.assertEqual(result["dimensions"], [720, 1280])
        self.assertEqual(result["audio"], "SILENT_VERIFIED")
        self.assertEqual(result["captions"], "UNKNOWN_HUMAN_REVIEW_REQUIRED")
        self.assertEqual(result["framing"], "UNKNOWN_HUMAN_REVIEW_REQUIRED")
        self.assertEqual(result["publication"], "NOT_RUN")
        with self.assertRaises(Invalid):
            inspect_output(self.store, "sample-two", job["result"]["render_id"])
        path, _ = artifact_file(self.store, APP, job["result"]["render_id"])
        path.write_bytes(b"changed")
        with self.assertRaises(Invalid):
            inspect_output(self.store, APP, job["result"]["render_id"])

    def create(self, selection, key):
        plan = Batch(self.store).plan(APP, selection)
        body = dict(plan=plan["plan_json"], plan_hash=plan["plan_hash"], request_key=key)
        envelope = dict(app_id=APP, operation="creative.batch.create", input=body)
        with bound_owner(self.store, envelope, self.identity, self.session, OWNER):
            with protected(self.store, envelope):
                return Batch(self.store).create(APP, body)

    def test_atomic_reservation_replay_and_rollback(self):
        selection = dict(variants=[self.request, dict(self.request, shape="LANDSCAPE")],
                         max_total_frames=2880, runtime="DESKTOP", expires=self.expires)
        calls = []
        def fail_second(*args):
            calls.append(1)
            if len(calls) == 2:
                raise Invalid("synthetic failure after first child")
            return enqueue_db(*args)
        with patch("mission_control.worker.enqueue_db", side_effect=fail_second):
            with self.assertRaises(Invalid):
                self.create(selection, "rollback-batch")
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM creative_batches").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)
        first = self.create(selection, "stable-batch")
        second = self.create(selection, "stable-batch")
        self.assertEqual(first["id"], second["id"])
        self.assertEqual([v["job_id"] for v in first["variants"]], [v["job_id"] for v in second["variants"]])
        self.assertEqual(len(jobs(self.store, APP)), 2)
        cancellation = dict(app_id=APP, operation="creative.batch.cancel", input={"batch_id": first["id"]})
        with bound_owner(self.store, cancellation, self.identity, self.session, OWNER), protected(self.store, cancellation):
            cancelled = Batch(self.store).cancel(APP, first["id"])
        self.assertEqual(cancelled["state"], "CANCELLED")
        self.assertTrue(all(job["status"] == "CANCELLED" for job in jobs(self.store, APP)))

    def test_revoked_owner_blocks_already_queued_render(self):
        selection = dict(variants=[self.request], max_total_frames=1440, runtime="DESKTOP", expires=self.expires)
        batch = self.create(selection, "revoked-owner")
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED' WHERE app_id=? AND principal=?", (APP, OWNER["principal"]))
        self.assertTrue(run_once(self.store))
        job = next(j for j in jobs(self.store, APP) if j["id"] == batch["variants"][0]["job_id"])
        self.assertEqual(job["status"], "BLOCKED")
        self.assertEqual(Renders(self.store).list(APP)["items"], [])

    def test_revoked_agent_grant_blocks_already_queued_render(self):
        grant_expiry = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        issued = Grants(self.store).issue(APP, OWNER, dict(agent_id="fixture-agent",
            manifest_version=self.store.app(APP)["version"], operations=["creative.batch.create"],
            expires=grant_expiry, max_calls=5))
        selection = dict(variants=[self.request], max_total_frames=1440, runtime="DESKTOP", expires=self.expires)
        reviewed = Batch(self.store).plan(APP, selection)
        body = dict(plan=reviewed["plan_json"], plan_hash=reviewed["plan_hash"], request_key="agent-fixture")
        envelope = dict(app_id=APP, operation="creative.batch.create", input=body)
        admission = Grants(self.store).admit(issued["token"], envelope)
        with bound_agent(self.store, envelope, admission):
            batch = execute(Service(self.store), envelope, caller="SCOPED_AGENT")
        Grants(self.store).revoke(APP, OWNER, dict(id=issued["grant"]["id"], version=1))
        self.assertTrue(run_once(self.store))
        job = next(j for j in jobs(self.store, APP) if j["id"] == batch["variants"][0]["job_id"])
        self.assertEqual(job["status"], "BLOCKED")
        self.assertEqual(Renders(self.store).list(APP)["items"], [])

    def test_real_batch_render_inspection_and_completion(self):
        selection = dict(variants=[self.request], max_total_frames=1440, runtime="DESKTOP", expires=self.expires)
        batch = self.create(selection, "real-batch")
        self.assertTrue(run_once(self.store))
        self.assertTrue(Batch(self.store).tick())
        result = next(item for item in Batch(self.store).list(APP)["items"] if item["id"] == batch["id"])
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["variants"][0]["inspection"]["decoded_frames"], 4)
        self.assertEqual(result["variants"][0]["inspection"]["captions"], "UNKNOWN_HUMAN_REVIEW_REQUIRED")

    def test_concurrent_reservations_do_not_exceed_aggregate_limit(self):
        selection = dict(variants=[self.request], max_total_frames=1440, runtime="DESKTOP", expires=self.expires)
        unit = Batch(self.store).plan(APP, selection)["plan"]["total_frames"]
        for index in range(11520 // unit - 1):
            self.create(selection, "fill-" + str(index))
        def admit(index):
            try:
                self.create(selection, "race-" + str(index))
                return "ADMITTED"
            except Invalid:
                return "REJECTED"
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(admit, range(2)))
        self.assertCountEqual(outcomes, ["ADMITTED", "REJECTED"])
        with connection(self.store.path) as db:
            self.assertLessEqual(db.execute("SELECT sum(reserved_frames) FROM creative_batches WHERE state='ACTIVE'").fetchone()[0], 11520)

    def test_expired_batch_lease_is_not_reclaimed_or_duplicated(self):
        selection = dict(variants=[self.request, dict(self.request, shape="LANDSCAPE")],
                         max_total_frames=2880, runtime="DESKTOP", expires=self.expires)
        batch = self.create(selection, "lease-expiry")
        attempt = claim(self.store)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=0 WHERE id=?", (attempt["id"],))
        self.assertIsNone(claim(self.store))
        result = Batch(self.store).list(APP)["items"][0]
        self.assertEqual(result["state"], "BLOCKED_HOLD")
        self.assertEqual(sorted(v["status"] for v in result["variants"]), ["BLOCKED", "CANCELLED"])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT attempts FROM jobs WHERE id=?", (attempt["id"],)).fetchone()[0], 1)
        self.assertTrue(ack_desktop_stop(self.store, attempt))  # Synthetic positive cleanup signal.
        cancel = dict(app_id=APP, operation="creative.batch.cancel", input={"batch_id": batch["id"]})
        with bound_owner(self.store, cancel, self.identity, self.session, OWNER), protected(self.store, cancel):
            self.assertEqual(Batch(self.store).cancel(APP, batch["id"])["state"], "CANCELLED")

    def test_uncertain_process_cleanup_retains_cancelled_reservation(self):
        selection = dict(variants=[self.request], max_total_frames=1440, runtime="DESKTOP", expires=self.expires)
        batch = self.create(selection, "uncertain-stop")
        @contextmanager
        def uncertain():
            yield dict(active=0, uncertain=True)
        def cancel_during_render(store, job, *args):
            cancellation = dict(app_id=APP, operation="creative.batch.cancel", input={"batch_id": batch["id"]})
            with bound_owner(self.store, cancellation, self.identity, self.session, OWNER), protected(self.store, cancellation):
                Batch(self.store).cancel(APP, batch["id"])
            raise Invalid("Synthetic uncertain subprocess cleanup")
        with patch("mission_control.media_native.track_children", side_effect=uncertain), \
             patch("mission_control.worker.process", side_effect=cancel_during_render):
            self.assertTrue(run_once(self.store))
        with connection(self.store.path) as db:
            row = db.execute("SELECT b.state,v.native_state FROM creative_batches b JOIN creative_batch_variants v ON v.batch_id=b.id WHERE b.id=?", (batch["id"],)).fetchone()
            self.assertEqual((row["state"], row["native_state"]), ("CANCEL_PENDING_HOLD", "STOP_PENDING"))

    def test_plan_data_bound_plan_guard_batch_guard_render_and_public_batch(self):
        selection = dict(variants=[self.request], max_total_frames=1440, runtime="DESKTOP", expires=self.expires)
        batch = self.create(selection, "guard-test")
        job = claim(self.store)
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (APP, batch["id"])).fetchone()
            self.assertEqual(plan_data(db, self.store, APP, selection), batch["plan"])
            self.assertEqual(bound_plan(row)["plan"], batch["plan"])
            self.assertEqual(guard_batch(db, self.store, row)["plan"], batch["plan"])
            self.assertIsNone(guard_render(db, self.store, job))
            self.assertEqual(public_batch(db, row)["id"], batch["id"])
            altered = dict(row); altered["plan_hash"] = "0" * 64
            with self.assertRaises(Invalid):
                bound_plan(altered)

    def test_copy_screens_checks_selected_source_bytes(self):
        with connection(self.store.path) as db:
            request = render_request(db, self.store, APP, self.request)
        with tempfile.TemporaryDirectory() as temporary:
            copies = Renders(self.store).copy_screens(Path(temporary), APP, request)
            self.assertEqual(len(copies), 1)
            self.assertTrue(copies[0].is_file())
            source = self.store.path.parent / "files" / APP / request["brief"]["data"]["content"]["screens"][0]["file_id"]
            source.write_bytes(b"changed")
            with self.assertRaises(Invalid):
                Renders(self.store).copy_screens(Path(temporary), APP, request)


if __name__ == "__main__":
    unittest.main()
