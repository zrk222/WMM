import threading
import unittest
from urllib.parse import parse_qs, urlsplit
from mission_control.hosted_login_flow import LoginFlow, MAX_PENDING, callback_fields, valid_binding
from mission_control.hosted_oidc import OIDCError, OIDCClient
from tests.test_hosted_oidc import config

ORIGIN = "http://127.0.0.1:8000"
REDIRECT = ORIGIN + "/auth/callback"


class Provider(OIDCClient):
    def __init__(self):
        super().__init__(config())
        self.calls = 0

    def exchange(self, code, verifier, nonce, redirect_uri):
        self.calls += 1
        return "identity"


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.provider = Provider()
        self.flow = LoginFlow(self.provider, clock=lambda: self.now)
        self.browser, self.csrf = self.flow.context()

    def start(self):
        url = self.flow.start(self.browser, self.csrf, ORIGIN, REDIRECT)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["code_challenge_method"], ["S256"])
        return query["state"][0]

    def callback(self, state):
        return self.flow.callback(self.browser, ORIGIN, REDIRECT, [("code", "code"), ("state", state)])

    def test_valid_binding_requires_exact_loopback_callback(self):
        self.assertTrue(valid_binding(ORIGIN, REDIRECT))
        for origin, target in (
            ("http://localhost:8000", REDIRECT),
            (ORIGIN, ORIGIN + "/other"),
            (ORIGIN + "/", REDIRECT),
        ):
            self.assertFalse(valid_binding(origin, target))

    def test_callback_fields_accepts_one_outcome_and_rejects_ambiguity(self):
        state = "A" * 43
        self.assertEqual(callback_fields([("error", "denied"), ("state", state)])["error"], "denied")
        for fields in (
            [("state", state), ("state", state)],
            [("code", "x"), ("state", "é" * 43)],
            [("code", "x"), ("other", state)],
        ):
            with self.subTest(fields=fields), self.assertRaises(OIDCError):
                callback_fields(fields)

    def test_one_use_and_commit(self):
        state = self.start()
        identity, generation = self.callback(state)
        self.assertEqual(identity, "identity")
        with self.assertRaises(OIDCError):
            self.callback(state)
        self.assertEqual(self.flow.commit_if_current(self.browser, generation, lambda: "session"), "session")
        with self.assertRaises(OIDCError):
            self.flow.commit_if_current(self.browser, generation, lambda: "session")

    def test_new_start_or_logout_invalidates_inflight_commit(self):
        state = self.start()
        _, generation = self.callback(state)
        self.start()
        with self.assertRaises(OIDCError):
            self.flow.commit_if_current(self.browser, generation, lambda: "session")
        state = self.start()
        _, generation = self.callback(state)
        self.flow.invalidate(self.browser)
        with self.assertRaises(OIDCError):
            self.flow.commit_if_current(self.browser, generation, lambda: "session")

    def test_invalid_binding_grammar_expiry_and_error(self):
        state = self.start()
        for params in ([("state", state), ("state", state)], [("code", "x"), ("state", state), ("extra", "x")]):
            with self.assertRaises(OIDCError):
                self.flow.callback(self.browser, ORIGIN, REDIRECT, params)
        with self.assertRaises(OIDCError):
            self.flow.callback("wrong", ORIGIN, REDIRECT, [("code", "x"), ("state", state)])
        with self.assertRaises(OIDCError):
            self.flow.callback(self.browser, ORIGIN, REDIRECT, [("error", "denied"), ("state", state)])
        with self.assertRaises(OIDCError):
            self.callback(state)
        state = self.start()
        self.now = 600
        with self.assertRaises(OIDCError):
            self.callback(state)
        self.assertEqual(self.provider.calls, 0)

    def test_cap_and_busy(self):
        for _ in range(MAX_PENDING - 1):
            self.flow.context()
        with self.assertRaises(OIDCError):
            self.flow.context()
        state = self.start()
        for _ in range(4):
            self.assertTrue(self.flow.slots.acquire(False))
        with self.assertRaises(OIDCError):
            self.callback(state)
        for _ in range(4):
            self.flow.slots.release()
        with self.assertRaises(OIDCError):
            self.callback(state)

    def test_concurrent_replay(self):
        state = self.start()
        barrier = threading.Barrier(2)
        results = []

        def run():
            barrier.wait()
            try:
                self.callback(state)
                results.append("ok")
            except OIDCError:
                results.append("rejected")

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["ok", "rejected"])
        self.assertEqual(self.provider.calls, 1)

    def test_failed_commit_is_not_reusable_and_cleanup_always_runs(self):
        state = self.start()
        _, generation = self.callback(state)

        def failed():
            raise ValueError("failed")

        with self.assertRaises(ValueError):
            self.flow.commit_if_current(self.browser, generation, failed)
        with self.assertRaises(OIDCError):
            self.flow.commit_if_current(self.browser, generation, lambda: None)
        seen = []
        self.flow.invalidate(self.browser, lambda: seen.append(True))
        self.flow.invalidate(self.browser, lambda: seen.append(True))
        self.assertEqual(seen, [True, True])

    def test_restart_rejects_pending_and_wrong_csrf(self):
        state = self.start()
        fresh = LoginFlow(self.provider, clock=lambda: self.now)
        with self.assertRaises(OIDCError):
            fresh.callback(self.browser, ORIGIN, REDIRECT, [("code", "x"), ("state", state)])
        with self.assertRaises(OIDCError):
            self.flow.start(self.browser, "wrong", ORIGIN, REDIRECT)

    def test_four_simultaneous_exchanges_and_late_completion(self):
        entered = threading.Barrier(5)
        release = threading.Event()
        results = []

        def exchange(*args):
            entered.wait(timeout=5)
            release.wait(timeout=5)
            return "identity"

        self.provider.exchange = exchange
        entries = [(self.browser, self.csrf)] + [self.flow.context() for _ in range(4)]
        states = []
        for browser, csrf in entries:
            url = self.flow.start(browser, csrf, ORIGIN, REDIRECT)
            states.append(parse_qs(urlsplit(url).query)["state"][0])

        def run(index):
            browser = entries[index][0]
            result = self.flow.callback(browser, ORIGIN, REDIRECT, [("code", "x"), ("state", states[index])])
            results.append((browser, result[1]))

        threads = [threading.Thread(target=run, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        entered.wait(timeout=5)
        with self.assertRaises(OIDCError):
            self.flow.callback(entries[4][0], ORIGIN, REDIRECT, [("code", "x"), ("state", states[4])])
        self.flow.start(entries[0][0], entries[0][1], ORIGIN, REDIRECT)
        self.flow.invalidate(entries[1][0])
        release.set()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(len(results), 4)
        for browser, generation in results:
            if browser in (entries[0][0], entries[1][0]):
                with self.assertRaises(OIDCError):
                    self.flow.commit_if_current(browser, generation, lambda: "session")
            else:
                self.assertEqual(self.flow.commit_if_current(browser, generation, lambda: "session"), "session")


if __name__ == "__main__":
    unittest.main()
