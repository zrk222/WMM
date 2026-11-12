"""Native owner expiry actions exercise real host identity and SQLite boundaries."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import unittest
from uuid import uuid4
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.db import connection
from tests import test_ios_agent_access as grants, test_ios_automation as standing


class NativeBridgeExpiryRouteContractTests(unittest.TestCase):
    def test_swift_and_objc_bridges_admit_exact_expiry_actions_in_both_domains(self):
        swift = Path("ios/WMM/Bridge/DomainBridge.swift").read_text(encoding="utf-8")
        objc = Path("ios/WMM/Bridge/EngineBootstrap.m").read_text(encoding="utf-8")
        expiry = ("extension-preview", "extension-confirm", "extension-history")
        swift_lists = {
            "automation": ("preview", "activate", "status", "off", *expiry),
            "agentAccess": (
                "list",
                "issue",
                "revoke",
                "handoff-list",
                "handoff-create",
                "handoff-revoke",
                *expiry,
            ),
        }
        objc_lists = {
            "automation": ("preview", "activate", "status", "off", *expiry),
            "agentAccess": (
                "list",
                "issue",
                "revoke",
                "handoff-list",
                "handoff-create",
                "handoff-revoke",
                *expiry,
            ),
        }
        for action, expected in swift_lists.items():
            with self.subTest(language="swift", action=action):
                match = re.search(
                    rf"func {action}\b[\s\S]*?guard \[(.*?)\]\.contains\(action\)",
                    swift,
                )
                self.assertIsNotNone(match)
                self.assertEqual(tuple(re.findall(r'"([^"]+)"', match.group(1))), expected)
        for action, expected in objc_lists.items():
            with self.subTest(language="objc", action=action):
                match = re.search(
                    rf"\+ \(NSData \*\){action}:[\s\S]*?BOOL known = \[@\[(.*?)\] containsObject:action\]",
                    objc,
                )
                self.assertIsNotNone(match)
                self.assertEqual(tuple(re.findall(r'@"([^"]+)"', match.group(1))), expected)


def future(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def confirm(preview):
    return dict(
        preview=preview["preview"],
        preview_hash=preview["preview_hash"],
        request_id=str(uuid4()),
        extended_expiry_consent=True,
    )


class NativeGrantExpiryTests(unittest.TestCase):
    setUp = grants.NativeAgentAccessTests.setUp
    verify = grants.NativeAgentAccessTests.verify
    creation = grants.NativeAgentAccessTests.creation
    manage = grants.NativeAgentAccessTests.manage
    issue = grants.NativeAgentAccessTests.issue
    call = grants.NativeAgentAccessTests.call

    def test_long_issuance_consent_and_extension_preserve_token_usage(self):
        with self.assertRaises(Invalid):
            self.issue(expires=future(48))
        issued = self.issue(expires=future(48), extended_expiry_consent=True)
        identity, token = issued["grant"]["id"], issued["token"]
        self.call(token)
        with connection(self.path) as db:
            before = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (identity,)).fetchone())
        review = self.manage("extension-preview", dict(kind="AGENT_GRANT", id=identity, expires=future(96)))
        self.assertEqual(review["preview"]["usage"]["used"], 1)
        body = confirm(review)
        with self.assertRaises(Invalid):
            self.manage("extension-confirm", dict(body, extended_expiry_consent=False))
        result = self.manage("extension-confirm", body)
        replay = self.manage("extension-confirm", body)
        self.assertEqual(result["receipt"]["receipt_hash"], replay["receipt"]["receipt_hash"])
        history = self.manage("extension-history", dict(kind="AGENT_GRANT", id=identity))
        self.assertGreaterEqual(len(history["receipts"]), 1)
        with connection(self.path) as db:
            after = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (identity,)).fetchone())
        for field in ("id", "token_hash", "used", "max_calls", "version"):
            self.assertEqual(before[field], after[field])
        self.call(token)

    def test_wrong_owner_locked_and_forged_kind_are_denied(self):
        issued = self.issue()
        body = dict(kind="AGENT_GRANT", id=issued["grant"]["id"], expires=future(48))
        review = self.manage("extension-preview", body)
        forged = confirm(review)
        forged["preview"] = dict(forged["preview"], kind="AUTOMATION")
        with self.assertRaises(Invalid):
            self.manage("extension-confirm", forged)
        self.available = False
        with self.assertRaises(PermissionError):
            self.manage("extension-confirm", confirm(review))
        self.available = True
        self.principal = str(uuid4())
        with self.assertRaises(PermissionError):
            self.manage("extension-preview", body)


class NativeAutomationExpiryTests(unittest.TestCase):
    setUp = standing.NativeStandingTests.setUp
    verify = standing.NativeStandingTests.verify
    creation = standing.NativeStandingTests.creation
    setup_standing = standing.NativeStandingTests.setup_standing
    vault = standing.NativeStandingTests.vault
    manage = standing.NativeStandingTests.manage
    proposal = standing.NativeStandingTests.proposal
    activate = standing.NativeStandingTests.activate

    def test_long_issuance_and_atomic_linked_extension(self):
        self.setup_standing()
        proposal = self.proposal()
        proposal["limits"]["expires"] = future(48)
        with self.assertRaises(Invalid):
            self.manage("preview", proposal)
        proposal["extended_expiry_consent"] = True
        preview = self.manage("preview", proposal)
        issued = self.manage(
            "activate", dict(proposal=preview["proposal"], summary_hash=preview["summary_hash"], confirm_scope=True)
        )
        identity = issued["policy_id"]
        with connection(self.path) as db:
            before = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (issued["grant"]["id"],)).fetchone())
        review = self.manage("extension-preview", dict(kind="AUTOMATION", id=identity, expires=future(96)))
        self.assertEqual(review["preview"]["bundle"][0]["id"], before["id"])
        self.manage("extension-confirm", confirm(review))
        self.assertTrue(self.manage("extension-history", dict(kind="AUTOMATION", id=identity))["receipts"])
        status = self.manage("status")["policies"][0]
        self.assertEqual(status["effective_status"], "ACTIVE")
        self.assertEqual(status["permission_expires_at"], review["preview"]["new_expiry"])
        self.assertIsNotNone(status["verification_due_at"])
        with connection(self.path) as db:
            after = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (before["id"],)).fetchone())
            linked = db.execute(
                "SELECT count(*) FROM authority_expiry_consents WHERE kind='AGENT_GRANT' AND authority_id=?",
                (before["id"],),
            ).fetchone()[0]
        for field in ("id", "token_hash", "used", "max_calls", "version"):
            self.assertEqual(before[field], after[field])
        self.assertGreaterEqual(linked, 2)


class NativeRetainedJobExpiryTests(NativeAutomationExpiryTests):
    def test_standing_job_cannot_inherit_extended_parent_at_entry_or_commit(self):
        from mission_control.ios_agent_access import NativeAgentAccess
        from mission_control.ios_automation import native_access
        from mission_control.ios_jobs import NativeJobs, native_pipeline_context
        from mission_control import worker

        self.setup_standing()
        preview = self.manage("preview", self.proposal(["pipeline_preparation"]))
        issued = self.manage(
            "activate", dict(proposal=preview["proposal"], summary_hash=preview["summary_hash"], confirm_scope=True)
        )
        agent = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        payload = json.dumps(
            dict(
                app_id="new-app",
                operation="pipeline.prepare",
                input=dict(action="pipeline", data=dict(stage=1), request_key="native-expiry-job"),
            )
        ).encode()
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with native_pipeline_context(self.runtime.service, self.runtime.identities, self.session):
                queued = json.loads(agent.call(self.session, issued["token"], payload))
        review = self.manage("extension-preview", dict(kind="AUTOMATION", id=issued["policy_id"], expires=future(48)))
        self.manage("extension-confirm", confirm(review))
        jobs = NativeJobs(self.runtime.service, self.runtime.identities)
        call = lambda: jobs.call(self.session, "new-app", "run", json.dumps(dict(id=queued["id"])).encode())
        late = datetime.now(timezone.utc) + timedelta(hours=2)
        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with patch("mission_control.complete_automation.utc", return_value=late):
                with self.assertRaisesRegex(PermissionError, "execution approval expired"):
                    call()
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?", (queued["id"],)).fetchone()[0], "QUEUED")
        # Advance the authority clock after processing, so the final commit must recheck it.
        clock = [datetime.now(timezone.utc)]
        original = worker.process

        def process_then_expire(*args):
            result = original(*args)
            clock[0] = late
            return result

        with native_access(self.runtime.service, self.runtime.identities, self.session, self.vault):
            with (
                patch("mission_control.complete_automation.utc", side_effect=lambda: clock[0]),
                patch.object(worker, "process", side_effect=process_then_expire),
            ):
                with self.assertRaisesRegex(PermissionError, "execution approval expired"):
                    call()
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT status FROM jobs WHERE id=?", (queued["id"],)).fetchone()[0], "RUNNING")


from tests import test_ios_standing_media as media


class NativeRetainedMediaExpiryTests(unittest.TestCase):
    setUp = media.NativeStandingMediaTests.setUp
    verify = media.NativeStandingMediaTests.verify
    creation = media.NativeStandingMediaTests.creation
    adapter = media.NativeStandingMediaTests.adapter
    owned = media.NativeStandingMediaTests.owned
    upload = media.NativeStandingMediaTests.upload
    decision = media.NativeStandingMediaTests.decision
    prepare_fixture = media.NativeStandingMediaTests.prepare_fixture
    scene = media.NativeStandingMediaTests.scene
    vault = media.NativeStandingMediaTests.vault
    proposal = media.NativeStandingMediaTests.proposal
    activate = media.NativeStandingMediaTests.activate
    agent = media.NativeStandingMediaTests.agent
    queue_scene = media.NativeStandingMediaTests.queue_scene
    host = media.NativeStandingMediaTests.host

    def test_standing_render_cannot_inherit_extended_parent(self):
        job = self.queue_scene()

        def manage(action, body):
            return json.loads(
                self.runtime.native_automation(self.session, "new-app", action, json.dumps(body).encode())
            )

        review = manage("extension-preview", dict(kind="AUTOMATION", id=self.issued["policy_id"], expires=future(48)))
        manage("extension-confirm", confirm(review))
        self.assertEqual(self.host("scene", "validate", job)["packet_hash"], job["packet_hash"])
        with patch(
            "mission_control.complete_automation.utc", return_value=datetime.now(timezone.utc) + timedelta(hours=2)
        ):
            with self.assertRaisesRegex(PermissionError, "execution approval expired"):
                self.host("scene", "validate", job)
        with connection(self.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM ios_studio_jobs WHERE id=?", (job["job_id"],)).fetchone()[0], "PREPARED"
            )


if __name__ == "__main__":
    unittest.main()
