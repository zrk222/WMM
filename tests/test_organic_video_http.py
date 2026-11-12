"""Actual loopback owner admission with temporary data and synthetic identities."""

import json
import hashlib
import http.client
import socket
import unittest
from urllib.error import HTTPError
from urllib.request import Request

from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import owner_domain_post
from tests import test_agent_grants as grants
from tests import test_agent_mcp as sdk
from tests import test_agent_review_clients as reviewed_clients
from tests import test_video_edit_clients as edit_clients
from tests.test_organic_video_discovery import bundle
from tests.test_organic_video_capture import OrganicVideoCaptureTests


BASE = "/api/apps/sample-one/organic-video/"


class OrganicDemoHTTPTests(unittest.TestCase):
    """Real owner transport; synthetic decoded MP4 and disposable workspace only."""

    setUp = grants.GrantTests.setUp
    tearDown = grants.GrantTests.tearDown
    body = grants.GrantTests.body
    issue = grants.GrantTests.issue

    @classmethod
    def setUpClass(cls):
        OrganicVideoCaptureTests.setUpClass.__func__(cls)

    def upload(self, selection=None, raw=None, path=BASE + "import-demo", **headers):
        value = dict(
            request_id="http-demo",
            manifest_version=1,
            release="build-1",
            filename="demo.mp4",
            source="OWNER_SELECTED_DEMO_MP4",
            app_owned=True,
            contains_private_data=False,
            uses_personal_account=False,
        )
        if selection is not None:
            value = selection
        fields = {
            "Origin": self.origin,
            "Content-Type": "application/octet-stream",
            "X-CSRF-Token": self.owner.csrf,
            "Cookie": "; ".join(c.name + "=" + c.value for c in self.owner.cookies),
            "X-WMM-Demo-Selection": json.dumps(value),
        }
        fields.update(headers)
        request = Request(self.origin + path, data=self.raw if raw is None else raw, method="POST", headers=fields)
        with self.owner.opener.open(request, timeout=10) as response:
            self.assertEqual(response.status, 201)
            return json.load(response)

    def test_exact_bytes_replay_and_separate_review(self):
        result = self.upload()
        self.assertEqual(result, self.upload())
        self.assertEqual(result["source_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(result["byte_count"], len(self.raw))
        item = self.owner.request("GET", "/api/apps/sample-one/media/" + result["media_id"])
        self.assertEqual(item["rights_status"], "UNKNOWN")
        self.assertEqual(item["review_history"], [])
        self.assertEqual(item["provenance"]["kind"], "OWNER_SELECTED_DEMO_MP4")
        with self.owner.opener.open(
            self.origin + "/api/apps/sample-one/media/" + result["media_id"] + "/download"
        ) as response:
            self.assertEqual(response.read(), self.raw)
        with self.assertRaises(HTTPError):
            self.upload(raw=self.raw + b"changed")
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM managed_media").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)

    def test_closed_selection_and_current_authority(self):
        value = dict(
            request_id="invalid-demo",
            manifest_version=1,
            release="build-1",
            filename="demo.mp4",
            source="OWNER_SELECTED_DEMO_MP4",
            app_owned=True,
            contains_private_data=False,
            uses_personal_account=False,
        )
        for change in (
            {"actor": "owner"},
            {"manifest_version": 2},
            {"release": "stale"},
            {"contains_private_data": True},
            {"filename": "../demo.mp4"},
        ):
            with self.assertRaises(HTTPError):
                self.upload(dict(value, **change))
        for headers, expected in (
            ({"X-CSRF-Token": "wrong"}, 403),
            ({"Origin": "http://foreign.invalid"}, 403),
            ({"Authorization": "Bearer forbidden"}, 403),
            ({"Content-Type": "application/json"}, 400),
            ({"X-WMM-Demo-Selection": '{"request_id":"a","request_id":"b"}'}, 400),
        ):
            with self.subTest(headers=tuple(headers)):
                with self.assertRaises(HTTPError) as error:
                    self.upload(**headers)
                with error.exception as response:
                    self.assertEqual(response.code, expected)
        # Reject an oversized declaration before sending any media bytes.
        with self.assertRaises(HTTPError) as error:
            self.upload(raw=b"", **{"Content-Length": "67108865"})
        with error.exception as response:
            self.assertEqual(response.code, 400)
            self.assertEqual(json.load(response)["error"], "Media input exceeds its bounded byte limit")
        with self.assertRaises(HTTPError):
            self.upload(path=BASE.replace("sample-one", "sample-two") + "import-demo")
        # This request can replace the opener's session cookie, so run it last.
        with self.assertRaises(HTTPError) as error:
            self.upload(Cookie="")
        with error.exception as response:
            self.assertEqual(response.code, 403)
        with connection(self.store.path) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='managed_media'").fetchone():
                self.assertEqual(db.execute("SELECT count(*) FROM managed_media").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)

    def test_truncated_body_cannot_commit(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        self.addCleanup(conn.close)
        conn.request(
            "POST",
            BASE + "import-demo",
            body=b"x",
            headers={
                "Origin": self.origin,
                "Content-Type": "application/octet-stream",
                "Content-Length": "100",
                "X-CSRF-Token": self.owner.csrf,
                "Cookie": "; ".join(c.name + "=" + c.value for c in self.owner.cookies),
                "X-WMM-Demo-Selection": "{}",
            },
        )
        conn.sock.shutdown(socket.SHUT_WR)
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        self.assertIn("truncated", response.read().decode())


class OrganicVideoHTTPTests(unittest.TestCase):
    tearDown = grants.GrantTests.tearDown
    body = grants.GrantTests.body
    issue = grants.GrantTests.issue

    def setUp(self):
        grants.GrantTests.setUp(self)
        self.issued = self.issue(["organic-video.claim", "organic-video.submit"], 20)
        self.request = dict(
            request_id="synthetic-video-research",
            query=dict(genre="personal growth", app_type="AI life coach", search_terms="habits"),
            policy=dict(
                recipient_grant_id=self.issued["grant"]["id"],
                platforms=["tiktok"],
                hosts=["www.tiktok.com"],
                expires=self.issued["grant"]["expires"],
                max_candidates=5,
                max_reads=100,
                max_seconds=600,
                access="PUBLIC_WEB",
            ),
        )

    def reject(self, path, body, status=None, client=None):
        with self.assertRaises(ClientError) as denied:
            (client or self.owner).request("POST", path, body)
        if status is not None:
            self.assertEqual(denied.exception.status, status)

    def test_owner_prepares_one_task_without_provider_or_publication(self):
        self.assertEqual(
            owner_domain_post(["api", "apps", "sample-one", "organic-video", "prepare"]).__module__,
            "mission_control.organic_video_http",
        )
        first = self.owner.request("POST", BASE + "prepare", self.request)
        self.assertEqual(first["status"], "READY")
        self.assertEqual(first["publication"], "NOT_RUN")
        self.assertEqual(first["provider_access"], "EXTERNAL_AGENT_NOT_VERIFIED")
        self.assertEqual(self.owner.request("POST", BASE + "prepare", self.request), first)
        self.assertNotIn(self.issued["token"], json.dumps(first))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM organic_discovery_tasks").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)

    def test_missing_identity_cross_app_changed_role_and_forged_actor_are_denied(self):
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        self.reject(BASE + "prepare", self.request, 403, anonymous)
        self.reject(BASE.replace("sample-one", "sample-two") + "prepare", self.request, 403)
        self.reject(BASE + "prepare", dict(self.request, actor="owner"), 400)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id='sample-one'")
        self.reject(BASE + "prepare", self.request, 403)

    def test_paths_framing_and_csrf_cannot_widen_owner_admission(self):
        for suffix in ("prepare?extra=1", "prepare/", "prepare%2f", "claim", "submit"):
            self.reject(BASE + suffix, self.request, 400)
        raw = json.dumps(self.request)
        duplicate = raw[:-1] + ',"request_id":"duplicate"}'
        for payload, csrf, origin, content_type in (
            (duplicate, self.owner.csrf, self.origin, "application/json"),
            (raw, "wrong", self.origin, "application/json"),
            (raw, self.owner.csrf, "http://foreign.invalid", "application/json"),
            (raw, self.owner.csrf, self.origin, "text/plain"),
        ):
            request = Request(
                self.origin + BASE + "prepare",
                data=payload.encode(),
                method="POST",
                headers={
                    "Origin": origin,
                    "Content-Type": content_type,
                    "X-CSRF-Token": csrf,
                    "Cookie": "; ".join(c.name + "=" + c.value for c in self.owner.cookies),
                },
            )
            with self.assertRaises(HTTPError) as denied:
                self.owner.opener.open(request, timeout=10)
            denied.exception.close()
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM sqlite_master WHERE name='organic_discovery_tasks'").fetchone()[0], 0
            )

    def test_bearer_cannot_prepare_or_borrow_owner_session(self):
        agent = OperatorClient(self.origin, grant_token=self.issued["token"])
        with self.assertRaises((ClientError, ValueError)):
            agent.request("POST", BASE + "prepare", self.request)
        request = Request(
            self.origin + BASE + "prepare",
            data=json.dumps(self.request).encode(),
            method="POST",
            headers={
                "Origin": self.origin,
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.issued["token"],
                "X-CSRF-Token": self.owner.csrf,
                "Cookie": "; ".join(c.name + "=" + c.value for c in self.owner.cookies),
            },
        )
        with self.assertRaises(HTTPError) as denied:
            self.owner.opener.open(request, timeout=10)
        denied.exception.close()

    def envelope(self, action, body, app="sample-one"):
        return dict(app_id=app, operation="organic-video." + action, input=body)

    def test_real_scoped_gateway_claim_submit_and_replay(self):
        saved = self.owner.request("POST", BASE + "prepare", self.request)
        agent = OperatorClient(self.origin, grant_token=self.issued["token"])
        claim_body = dict(task_id=saved["id"], task_hash=saved["task_hash"])
        claimed = agent.call(self.envelope("claim", claim_body))
        self.assertEqual(claimed["status"], "CLAIMED")
        self.assertEqual(agent.call(self.envelope("claim", claim_body)), claimed)
        result = bundle(saved["task"])
        result.update(task_id=saved["id"], task_hash=saved["task_hash"], claim_id=claimed["claim_id"])
        body = dict(task_id=saved["id"], result=result)
        completed = agent.call(self.envelope("submit", body))
        self.assertEqual(completed["status"], "SUBMITTED")
        self.assertEqual(completed["result"]["collection_verification"], "REQUIRED")
        self.assertEqual(agent.call(self.envelope("submit", body)), completed)
        self.assertEqual(completed["publication"], "NOT_RUN")
        self.assertEqual(len(agent.cookies), 0)
        self.assertNotIn(self.issued["token"], json.dumps(completed))

    def test_gateway_recipient_grant_and_lease_revocation_are_current(self):
        saved = self.owner.request("POST", BASE + "prepare", self.request)
        body = dict(task_id=saved["id"], task_hash=saved["task_hash"])
        other = self.issue(["organic-video.claim", "organic-video.submit"], 20)
        foreign = OperatorClient(self.origin, grant_token=other["token"])
        with self.assertRaises(ClientError):
            foreign.call(self.envelope("claim", body))
        agent = OperatorClient(self.origin, grant_token=self.issued["token"])
        with self.assertRaises(ClientError):
            agent.call(self.envelope("claim", body, "sample-two"))
        claimed = agent.call(self.envelope("claim", body))
        result = bundle(saved["task"])
        result.update(task_id=saved["id"], task_hash=saved["task_hash"], claim_id=claimed["claim_id"])
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE organic_discovery_tasks SET claim_until='2000-01-01T00:00:00+00:00' WHERE id=?", (saved["id"],)
            )
        with self.assertRaises(ClientError):
            agent.call(self.envelope("submit", dict(task_id=saved["id"], result=result)))
        self.owner.request(
            "POST", "/api/apps/sample-one/agent-grants/revoke", dict(id=self.issued["grant"]["id"], version=1)
        )
        with self.assertRaises(ClientError):
            agent.call(self.envelope("claim", body))


@unittest.skipUnless(sdk.HAS_MCP, "Official MCP SDK required for collector transport acceptance")
class OrganicVideoClientTests(unittest.IsolatedAsyncioTestCase):
    setUp = OrganicVideoHTTPTests.setUp
    tearDown = grants.GrantTests.tearDown
    body = grants.GrantTests.body
    issue = grants.GrantTests.issue
    envelope = OrganicVideoHTTPTests.envelope
    cli = edit_clients.VideoClientsTests.cli
    session = reviewed_clients.ReviewClientTests.session

    async def test_cli_claim_and_mcp_submit_share_exact_saved_task(self):
        self.token = self.issued["token"]
        saved = self.owner.request("POST", BASE + "prepare", self.request)
        claim_body = dict(task_id=saved["id"], task_hash=saved["task_hash"])
        claimed = self.cli(self.envelope("claim", claim_body))
        result = bundle(saved["task"])
        result.update(task_id=saved["id"], task_hash=saved["task_hash"], claim_id=claimed["claim_id"])
        request = dict(task_id=saved["id"], result=result)
        async with self.session() as client:
            names = {row.name for row in (await client.list_tools()).tools}
            self.assertIn("wmm_organic-video_claim", names)
            self.assertIn("wmm_organic-video_submit", names)
            completed = await client.call_tool("wmm_organic-video_submit", dict(app_id="sample-one", input=request))
            self.assertFalse(completed.isError, completed.content)
            data = completed.structuredContent["data"]
            self.assertEqual(data["status"], "SUBMITTED")
            self.assertEqual(data["publication"], "NOT_RUN")
            self.assertEqual(self.cli(self.envelope("submit", request)), data)


if __name__ == "__main__":
    unittest.main()
