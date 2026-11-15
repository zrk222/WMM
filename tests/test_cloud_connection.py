"""Personal cloud is optional; local is the default and tokens never enter SQLite."""

from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import tempfile
import unittest
from unittest.mock import patch

from mission_control.cloud_connection import CloudConnections
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.store import Store
from tests.test_cloud_ingest import Handler, TOKEN

OWNER = {"principal": "github:1", "login": "owner"}
APP = "sample-one"


class FakeVault:
    def __init__(self):
        self.values = {}

    def put(self, name, value):
        self.values[name] = dict(value)

    def get(self, name):
        return self.values.get(name)

    def delete(self, name):
        self.values.pop(name, None)


class CloudConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.calls.clear()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.endpoint = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "state.sqlite"
        self.store = Store(self.path, seed=False)
        self.store.save_app(
            APP,
            dict(
                name="Synthetic app",
                release="build-1",
                job="Synthetic job",
                audience="Synthetic audience",
                activation="Synthetic value",
                locale="en-US",
            ),
        )
        self.vault = FakeVault()
        self.clouds = CloudConnections(self.store, self.vault)

    def test_local_is_default_and_does_not_require_a_token(self):
        value = self.clouds.current(APP)
        self.assertEqual((value["mode"], value["status"]), ("LOCAL", "LOCAL"))
        self.assertEqual(self.vault.values, {})

    def test_save_test_and_return_to_local_without_plaintext_token(self):
        saved = self.clouds.save(APP, OWNER, {"endpoint": self.endpoint, "token": TOKEN})
        self.assertEqual(saved["mode"], "PERSONAL_CLOUD")
        self.assertEqual(saved["status"], "CONFIGURED_UNTESTED")
        with connection(self.path) as db:
            self.assertNotIn(TOKEN, "\n".join(db.iterdump()))
        self.assertEqual(self.clouds.test(APP)["status"], "TESTED")
        self.assertEqual(self.clouds.current(APP)["status"], "TESTED")
        removed = self.clouds.remove(APP)
        self.assertEqual(removed["cleanup"], "REMOVED")
        self.assertEqual(self.clouds.current(APP)["mode"], "LOCAL")
        self.assertEqual(self.vault.values, {})

    def test_test_without_connection_stays_local_and_explicit(self):
        with self.assertRaises(Exception):
            self.clouds.test(APP)
        self.assertEqual(self.clouds.current(APP)["mode"], "LOCAL")

    def test_endpoint_change_requires_a_new_token(self):
        original = self.clouds.save(APP, OWNER, {"endpoint": self.endpoint, "token": TOKEN})
        with self.assertRaisesRegex(Invalid, "new token"):
            self.clouds.save(APP, OWNER, {"endpoint": "https://replacement.example"})
        self.assertEqual(self.clouds.current(APP), original)
        self.assertEqual(len(self.vault.values), 1)

    def test_late_health_response_cannot_verify_replacement(self):
        self.clouds.save(APP, OWNER, {"endpoint": self.endpoint, "token": TOKEN})

        def replace_during_health():
            self.clouds.save(APP, OWNER, {"endpoint": "https://replacement.example", "token": "replacement-test-token"})
            return {"tenant": "old", "version": "1"}

        with patch("mission_control.cloud_connection.CloudIngest.health", side_effect=replace_during_health):
            with self.assertRaisesRegex(Invalid, "changed during the test"):
                self.clouds.test(APP)
        self.assertEqual(self.clouds.current(APP)["status"], "CONFIGURED_UNTESTED")
        self.assertEqual(self.clouds.current(APP)["endpoint"], "https://replacement.example")
