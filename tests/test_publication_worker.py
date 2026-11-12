import time, unittest
from unittest.mock import patch
from mission_control import worker, publication_schedule, publication_sessions
from mission_control.publication_transport import Context
from mission_control.db import connection
from tests import test_publication_authority as fixtures

APP = fixtures.APP


class Vault:
    data = {}

    def get(self, k):
        return self.data.get(k)

    def put(self, k, v):
        self.data[k] = v

    def delete(self, k):
        self.data.pop(k, None)


def state(status, remote=None):
    return {"status": status, "remote_id": remote, "asset_id": None, "session": None, "observation": {}}


class PublicationWorkerTests(unittest.TestCase):
    setUp = fixtures.PublicationAuthorityTests.setUp
    call = fixtures.PublicationAuthorityTests.call
    prepare = fixtures.PublicationAuthorityTests.prepare
    activate = fixtures.PublicationAuthorityTests.activate

    def enqueue(self):
        item = self.prepare()
        self.activate(item, max_calls=30)
        return item, self.call(
            "publication.execute",
            {"id": item["id"]},
            lambda: publication_schedule.enqueue_approved(self.store, APP, item["id"]),
        )

    def test_three_actual_worker_phases_and_no_generic_result_overwrite(self):
        item, schedule = self.enqueue()
        vault = Vault()
        vault.data = {}

        def ctx(store, app, draft, before, heartbeat):
            return Context("linkedin", draft["destination_id"], "token", before, heartbeat)

        def create(draft, artifact, context):
            return state("READY_TO_PUBLISH")

        def publish(draft, previous, context):
            context.before_call()
            return state("PUBLISH_ACKNOWLEDGED", "urn:li:share:12")

        def read(draft, previous, context):
            context.before_call()
            return state("PUBLISHED", "urn:li:share:12")

        with (
            patch.object(publication_sessions, "Vault", return_value=vault),
            patch("mission_control.publication_credentials.context", side_effect=ctx),
            patch("mission_control.publication_linkedin.create", side_effect=create),
            patch("mission_control.publication_linkedin.publish", side_effect=publish),
            patch("mission_control.publication_linkedin.read", side_effect=read),
        ):
            for expected in ("READY_TO_PUBLISH", "PUBLISH_ACKNOWLEDGED", "PUBLISHED"):
                self.assertTrue(worker.run_once(self.store))
                with connection(self.store.path) as db:
                    job = db.execute(
                        "SELECT status,attempts,result FROM jobs WHERE id=?", (schedule["job_id"],)
                    ).fetchone()
                    import json

                    self.assertEqual(json.loads(job["result"])["status"], expected)
                    db.execute(
                        "UPDATE publication_schedules SET next_due=? WHERE id=?", (time.time() - 1, schedule["id"])
                    )
            self.assertEqual(job["attempts"], 3)

    def test_expired_running_is_blocked_not_reclaimed(self):
        _, schedule = self.enqueue()
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?", (time.time() - 1, schedule["job_id"])
            )
        self.assertIsNone(worker.claim(self.store))
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM jobs WHERE id=?", (schedule["job_id"],)).fetchone()[0], "BLOCKED"
            )
            self.assertEqual(
                db.execute("SELECT status FROM publication_schedules WHERE id=?", (schedule["id"],)).fetchone()[0],
                "BLOCKED",
            )

    def test_attempts_beyond_three_remain_claimable(self):
        _, schedule = self.enqueue()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET attempts=3 WHERE id=?", (schedule["job_id"],))
        job = worker.claim(self.store)
        self.assertEqual(job["attempts"], 4)


if __name__ == "__main__":
    unittest.main()
