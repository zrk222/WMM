"""Real owner-session history and adoption readback; isolated synthetic workspace."""

import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mission_control.common import digest
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import Server
from tests import test_organic_video_intake as intake
from tests import test_verified_review as identities


class ResearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f = intake.IntakeTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store, self.app = self.f.store, self.f.app

        def identity(path, token):
            return dict(identities.synthetic_identity(path, token), **self.f.fixture.owner)

        mocked = patch("mission_control.operator_identity.github_read", side_effect=identity)
        mocked.start()
        self.addCleanup(mocked.stop)
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.client = OperatorClient(self.origin)
        self.client.bootstrap()
        self.client.request("POST", "/api/identity/login", dict(token=identities.OWNER_TOKEN))
        self.base = "/api/apps/" + self.app + "/organic-video/"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, action, body):
        result = self.client.request("POST", self.base + action, body)
        assert isinstance(result, dict)
        return result

    def test_owner_history_request_identity_and_exact_adoption_readback(self):
        page = self.call("task-list", dict(offset=0, request_id=None))
        self.assertEqual(len(page["items"]), 1)
        self.assertEqual(page["items"][0]["candidate_count"], 1)
        self.assertEqual(page["items"][0]["reviewable_count"], 1)
        row = page["items"][0]
        self.assertEqual(row["id"], self.f.body["task_id"])
        self.assertEqual(row["request_hash"], digest(self.f.fixture.body))
        self.assertIsNone(page["next_offset"])
        selected = self.call("task-list", dict(offset=0, request_id=row["request_id"]))
        self.assertEqual(selected["items"], page["items"])
        self.assertEqual(self.call("task-list", dict(offset=0, request_id="absent"))["items"], [])
        self.assertNotIn("submission", row)
        self.assertNotIn("token", json.dumps(page))
        saved = self.f.call()
        detail = self.call("task-read", dict(task_id=row["id"]))
        self.assertEqual(detail["intakes"][0]["id"], saved["id"])
        self.assertEqual(detail["intakes"][0]["request_hash"], digest(self.f.body))
        self.assertEqual(detail["intakes"][0]["data"]["publication"], "NOT_RUN")
        history = self.call("task-list", dict(offset=0, request_id=None))
        self.assertEqual(history["items"][0]["intakes"][0]["id"], saved["id"])
        self.assertEqual(history["items"][0]["intakes"][0]["source_id"], saved["data"]["source"]["id"])

    def test_other_owner_and_app_are_excluded_before_returning_private_data(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE organic_discovery_tasks SET owner='github:other-owner'")
        self.assertEqual(self.call("task-list", dict(offset=0, request_id=None))["items"], [])
        with self.assertRaises(ClientError):
            self.call("task-read", dict(task_id=self.f.body["task_id"]))
        with self.assertRaises(ClientError):
            self.client.request("POST", "/api/apps/other-app/organic-video/task-list", dict(offset=0, request_id=None))

    def test_history_rejects_malformed_bounds_and_keeps_filter_as_data(self):
        for body in [dict(offset=x, request_id=None) for x in (-1, True, 1.5, 100001)] + [
            dict(offset=0, request_id=""),
            dict(offset=0, request_id=None, owner="forged"),
        ]:
            with self.subTest(body=body), self.assertRaises(ClientError):
                self.call("task-list", body)
        self.assertEqual(self.call("task-list", dict(offset=0, request_id="' OR 1=1 --"))["items"], [])

    def test_pagination_is_stable_and_bounded(self):
        with connection(self.store.path) as db:
            original = dict(db.execute("SELECT * FROM organic_discovery_tasks").fetchone())
            for index in range(22):
                values = dict(original, id="history-" + str(index).zfill(2), request_id="page-" + str(index))
                db.execute(
                    "INSERT INTO organic_discovery_tasks ("  # noqa: S608 - columns come from the fixture table.
                    + ",".join(values)
                    + ") VALUES ("
                    + ",".join("?" for _ in values)
                    + ")",
                    tuple(values.values()),
                )
        first = self.call("task-list", dict(offset=0, request_id=None))
        second = self.call("task-list", dict(offset=first["next_offset"], request_id=None))
        self.assertEqual((len(first["items"]), len(second["items"])), (20, 3))
        self.assertEqual(len({x["id"] for x in first["items"] + second["items"]}), 23)
        self.assertIsNone(second["next_offset"])

    def test_owner_session_csrf_and_bearer_exclusion_cover_new_read_route(self):
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request("POST", self.base + "task-list", dict(offset=0, request_id=None))
        csrf = self.client.csrf
        assert isinstance(csrf, str)
        for extra in ({"X-CSRF-Token": "wrong"}, {"Authorization": "Bearer not-a-browser-owner"}):
            headers = {
                "Origin": self.origin,
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
                "Cookie": "; ".join(c.name + "=" + (c.value or "") for c in self.client.cookies),
                **extra,
            }
            req = Request(
                self.origin + self.base + "task-list",
                json.dumps(dict(offset=0, request_id=None)).encode(),
                headers,
                method="POST",
            )
            with self.subTest(extra=extra), self.assertRaises(HTTPError) as caught:
                urlopen(req, timeout=5)
            self.assertEqual(caught.exception.code, 403)

    def test_static_script_is_served_through_exact_allowlist(self):
        with urlopen(self.origin + "/organic-research.js", timeout=5) as response:
            self.assertIn("javascript", response.headers["Content-Type"])
            self.assertEqual(
                response.read(), (Path(__file__).parents[1] / "mission_control/static/organic-research.js").read_bytes()
            )
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.origin + "/unknown-research.js", timeout=5)
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
