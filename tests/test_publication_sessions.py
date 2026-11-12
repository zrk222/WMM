import copy, unittest, uuid
from unittest.mock import patch
from types import SimpleNamespace
from mission_control.common import Invalid, canonical
from mission_control import publication_sessions as s


class FakeVault:
    data = {}
    fail_at = None
    writes = 0

    def get(self, k):
        return copy.deepcopy(self.data.get(k))

    def put(self, k, v):
        if len(canonical(v).encode()) > 2560:
            raise AssertionError("native blob overflow")
        self.writes += 1
        if self.fail_at == self.writes:
            raise Invalid("vault locked")
        self.data[k] = copy.deepcopy(v)

    def delete(self, k):
        self.data.pop(k, None)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.v = FakeVault()
        self.v.data = {}
        self.store = SimpleNamespace(path="fake.sqlite")
        self.intent = str(uuid.uuid4())
        self.check = str(uuid.uuid4())
        self.hash = "a" * 64
        self.state = {
            "status": "CREATED",
            "remote_id": None,
            "asset_id": "urn:li:video:1",
            "session": {"urls": ["https://www.linkedin.com/dms-uploads/" + ("x" * 500) + str(i) for i in range(16)]},
            "observation": {},
        }
        self.p = patch.object(s, "Vault", return_value=self.v)
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_large_roundtrip_bindings_and_retire(self):
        s.retain(self.store, "test-app", self.intent, self.hash, self.check, self.state)
        self.assertGreater(len(self.v.data), 2)
        self.assertEqual(s.load(self.store, "test-app", self.intent, self.hash, self.check), self.state)
        for app, intent, h, check in [
            ("other", self.intent, self.hash, self.check),
            ("test-app", str(uuid.uuid4()), self.hash, self.check),
            ("test-app", self.intent, "b" * 64, self.check),
            ("test-app", self.intent, self.hash, str(uuid.uuid4())),
        ]:
            with self.assertRaises(Invalid):
                s.load(self.store, app, intent, h, check)
        s.retire(self.store, "test-app", self.intent, self.check)
        self.assertEqual(self.v.data, {})

    def test_partial_and_tamper_fail_closed(self):
        self.v.fail_at = 2
        with self.assertRaises(Invalid):
            s.retain(self.store, "test-app", self.intent, self.hash, self.check, self.state)
        with self.assertRaises(Invalid):
            s.load(self.store, "test-app", self.intent, self.hash, self.check)
        self.v.fail_at = None
        s.retain(self.store, "test-app", self.intent, self.hash, self.check, self.state)
        key = next(k for k in self.v.data if k.endswith("/0"))
        self.v.data[key]["data"] = "A" + self.v.data[key]["data"][1:]
        with self.assertRaises(Invalid):
            s.load(self.store, "test-app", self.intent, self.hash, self.check)

    def test_bound_and_conflict(self):
        with self.assertRaises(Invalid):
            s.retain(self.store, "test-app", self.intent, self.hash, self.check, {**self.state, "session": "x" * 70000})
        s.retain(self.store, "test-app", self.intent, self.hash, self.check, self.state)
        with self.assertRaises(Invalid):
            s.retain(self.store, "test-app", self.intent, self.hash, self.check, {**self.state, "status": "OTHER"})


if __name__ == "__main__":
    unittest.main()
