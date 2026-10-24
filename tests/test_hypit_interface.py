"""Actual owner/bearer HTTP, CLI and MCP routes over synthetic private media."""

import hashlib
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.hypit_jobs import artifact_file
from mission_control.common import Invalid
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.worker import run_once, jobs
from tests import test_agent_grants as fixture
from tests import test_agent_mcp as sdk
from tests import test_agent_review_clients as clients
from tests.test_creative_rendering import prepared_render

APP = "sample-one"
CONTENT = (
    b"Synthetic private media transport fixture; decoded runtime tested separately"
)
KEY = "bld_20261024_HTTP1234"


class HypitInterfaceTests(unittest.IsolatedAsyncioTestCase):
    body = fixture.GrantTests.body
    envelope = fixture.GrantTests.envelope
    session = clients.ReviewClientTests.session

    def setUp(self):
        fixture.GrantTests.setUp(self)
        app = self.store.app(APP)
        self.store.save_app(
            APP,
            dict(
                app["data"],
                job="Synthetic job",
                audience="Synthetic audience",
                activation="Saved fictional step",
            ),
            app["version"],
        )
        self.brief, self.request = prepared_render(self.store, APP)
        self.launcher = patch(
            "mission_control.hypit_jobs.identity",
            return_value=dict(launcher="fixture", launcher_sha256="0" * 64),
        )
        self.launcher.start()

    def tearDown(self):
        self.launcher.stop()
        fixture.GrantTests.tearDown(self)

    def grant(self, operations):
        body = dict(
            self.body(operations, 100), manifest_version=self.store.app(APP)["version"]
        )
        issued = self.owner.request(
            "POST", "/api/apps/" + APP + "/agent-grants/issue", body
        )
        self.token = issued["token"]
        return OperatorClient(self.origin, grant_token=self.token)

    def adapter(self, folder, scene, alive, submitted):
        alive()
        submitted(KEY)
        (folder / "video.mp4").write_bytes(CONTENT)
        return dict(
            build_id=KEY,
            artifact=dict(
                bytes=len(CONTENT), sha256=hashlib.sha256(CONTENT).hexdigest()
            ),
            cleanup=dict(worker="STOPPED"),
            publication="NOT_RUN",
        )

    def payload(self, key="http-hypit"):
        return dict(data=self.request, request_key=key)

    def test_owner_workspace_queue_and_history_use_the_durable_service(self):
        with patch(
            "mission_control.hypit_jobs.render", side_effect=self.adapter
        ) as runtime:
            view = self.owner.request("GET", "/api/apps/" + APP)
            self.assertEqual(view["hypit_renders"]["items"], [])
            self.assertEqual(view["hypit_renders"]["capability"]["status"], "DETECTED")
            runtime.assert_not_called()
            queued = self.owner.request(
                "POST", "/api/apps/" + APP + "/production/hypit-renders", self.payload()
            )
            self.assertEqual(
                self.owner.request(
                    "POST",
                    "/api/apps/" + APP + "/production/hypit-renders",
                    self.payload(),
                )["id"],
                queued["id"],
            )
            self.assertTrue(run_once(self.store))
            history = self.owner.request("GET", "/api/apps/" + APP + "/hypit-renders")
            self.assertEqual(history["items"][0]["job_id"], queued["id"])
            self.assertEqual(history["attempts"][0]["data"]["build_id"], KEY)
            self.assertEqual(runtime.call_count, 1)
            self.assertEqual(
                self.owner.request("GET", "/api/apps/sample-two/hypit-renders")[
                    "items"
                ],
                [],
            )

    def test_video_bytes_range_download_scope_and_checksum(self):
        self.owner.request(
            "POST", "/api/apps/" + APP + "/production/hypit-renders", self.payload()
        )
        with patch("mission_control.hypit_jobs.render", side_effect=self.adapter):
            run_once(self.store)
        identity = jobs(self.store, APP)[0]["result"]["render_id"]
        base = "/api/apps/" + APP + "/hypit-renders/" + identity
        for suffix in ("preview", "download"):
            with self.owner.opener.open(
                Request(
                    self.origin + base + "/" + suffix, headers={"Origin": self.origin}
                )
            ) as response:
                self.assertEqual(response.headers.get_content_type(), "video/mp4")
                self.assertEqual(response.read(), CONTENT)
                if suffix == "download":
                    self.assertIn("attachment", response.headers["Content-Disposition"])
        with self.owner.opener.open(
            Request(
                self.origin + base + "/preview",
                headers={"Origin": self.origin, "Range": "bytes=2-8"},
            )
        ) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), CONTENT[2:9])
        for path in (
            base + "/preview?extra=1",
            base + "/unknown",
            base.replace(APP, "sample-two") + "/download",
            base.replace("hypit-renders", "renders") + "/preview",
        ):
            with self.assertRaises(HTTPError):
                self.owner.opener.open(
                    Request(self.origin + path, headers={"Origin": self.origin})
                )
        path, _ = artifact_file(self.store, APP, identity)
        path.write_bytes(b"changed")
        with self.assertRaises(HTTPError):
            self.owner.opener.open(
                Request(
                    self.origin + base + "/preview", headers={"Origin": self.origin}
                )
            )

    def test_agent_scope_schema_and_generic_job_bypass_are_enforced(self):
        agent = self.grant(["hypit.read", "pipeline.prepare"])
        self.assertEqual(agent.call(self.envelope("hypit.read"))["items"], [])
        for envelope in (
            self.envelope("hypit.queue", self.payload()),
            self.envelope("hypit.read", app_id="sample-two"),
            self.envelope(
                "pipeline.prepare",
                dict(action="hypit_render", data={}, request_key="bypass"),
            ),
        ):
            with self.assertRaises((ClientError, Invalid)):
                agent.call(envelope)
        with self.assertRaises(ClientError):
            self.owner.request(
                "POST",
                "/api/apps/" + APP + "/jobs",
                dict(action="hypit_render", data={}, request_key="http-bypass"),
            )
        self.assertEqual(jobs(self.store, APP), [])
        agent = self.grant(["hypit.queue"])
        for body in (
            dict(self.payload(), shell="arbitrary"),
            dict(data=dict(self.request, path="../unsafe"), request_key="extra"),
        ):
            with self.assertRaises((ClientError, Invalid)):
                agent.call(self.envelope("hypit.queue", body))
        self.assertEqual(jobs(self.store, APP), [])

    @unittest.skipUnless(
        sdk.HAS_MCP, "Official MCP SDK required for two-client acceptance"
    )
    async def test_cli_queue_then_actual_mcp_history_uses_same_job_and_grant(self):
        self.grant(["hypit.queue", "hypit.read", "jobs.read"])
        envelope = self.envelope("hypit.queue", self.payload("cli-hypit"))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mission_control.agent_cli",
                "call",
                "--origin",
                self.origin,
                "--use-grant",
            ],
            input=json.dumps(envelope).encode(),
            capture_output=True,
            env=dict(os.environ, WMM_AGENT_GRANT=self.token),
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertNotIn(self.token, result.stdout.decode())
        queued = json.loads(result.stdout)
        async with self.session() as client:
            tools = {tool.name for tool in (await client.list_tools()).tools}
            self.assertTrue({"wmm_hypit_read", "wmm_hypit_queue"} <= tools)
            with patch("mission_control.hypit_jobs.render", side_effect=self.adapter):
                self.assertTrue(run_once(self.store))
            response = await client.call_tool(
                "wmm_hypit_read", dict(app_id=APP, input={})
            )
            self.assertFalse(response.isError, response.content)
            self.assertEqual(
                response.structuredContent["data"]["items"][0]["job_id"], queued["id"]
            )
            response = await client.call_tool(
                "wmm_hypit_queue",
                dict(app_id="sample-two", input=self.payload("foreign")),
            )
            self.assertTrue(response.isError)
