"""Offline protocol and privacy boundaries for native OpenSEO reads."""

from __future__ import annotations

import json
import unittest
from email.message import Message
from types import TracebackType
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from mission_control import openseo_transport as transport
from mission_control.insights_transport import ProviderFailure
from mission_control.providers import NoRedirect


def envelope(result: dict, identity: int = 2) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": identity, "result": result}).encode()


class Response:
    def __init__(
        self, raw: bytes, status: int = 200, content_type: str = "application/json", session: str | None = None
    ) -> None:
        self.raw, self.status = raw, status
        self.headers = {"Content-Type": content_type}
        if session:
            self.headers["Mcp-Session-Id"] = session

    def __enter__(self) -> Response:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None
    ) -> bool:
        return False

    def read(self, size: int) -> bytes:
        return self.raw[:size]


class TransportTests(unittest.TestCase):
    def run_call(self, last: Response, first: Response | None = None) -> tuple[dict, MagicMock]:
        responses = [
            first or Response(envelope({"protocolVersion": transport.PROTOCOL}, 1), session="session-1"),
            Response(b"", 202),
            last,
        ]
        with patch.object(transport, "build_opener") as build:
            build.return_value.open.side_effect = responses
            result = transport.call_tool("synthetic-token", "get_project_context", {"projectId": "p"})
            return result, build

    def test_handshake_session_fixed_destination_and_structured_only(self) -> None:
        result, build = self.run_call(Response(envelope({"structuredContent": {"project": "p"}})))
        self.assertEqual(result, {"project": "p"})
        self.assertIsInstance(build.call_args.args[0], NoRedirect)
        calls = build.return_value.open.call_args_list
        bodies = [json.loads(c.args[0].data) for c in calls]
        self.assertEqual([b["method"] for b in bodies], ["initialize", "notifications/initialized", "tools/call"])
        self.assertEqual(bodies[-1]["params"], {"name": "get_project_context", "arguments": {"projectId": "p"}})
        for index, call in enumerate(calls):
            request = call.args[0]
            self.assertEqual(request.full_url, transport.ENDPOINT)
            self.assertEqual(call.kwargs["timeout"], 15)
            self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-token")
            self.assertEqual(request.get_header("Mcp-protocol-version"), transport.PROTOCOL)
            if index:
                self.assertEqual(request.get_header("Mcp-session-id"), "session-1")

    def test_deny_mutation_before_network(self) -> None:
        with patch.object(transport, "build_opener") as build:
            for tool in ["create_project", "run_audit", "publish_article", "tools/list"]:
                with self.assertRaises(ProviderFailure) as caught:
                    transport.call_tool("secret", tool, {})
                self.assertEqual(caught.exception.code, "TOOL_DENIED")
            build.assert_not_called()

    def test_sse_and_bound(self) -> None:
        raw = b": ping\r\n\r\ndata: " + envelope({"structuredContent": {"ok": True}}) + b"\r\n\r\n"
        result, _ = self.run_call(Response(raw, content_type="text/event-stream; charset=utf-8"))
        self.assertEqual(result, {"ok": True})
        with self.assertRaises(ProviderFailure) as caught:
            self.run_call(Response(b" " * (transport.LIMIT + 1), content_type="text/event-stream"))
        self.assertEqual(caught.exception.code, "RESPONSE_TOO_LARGE")

    def test_invalid_responses_fail_closed(self) -> None:
        for raw in [
            b"not json",
            envelope({}, 4),
            envelope({"content": [{"text": "invented"}]}),
            b'{"jsonrpc":"2.0","id":2,"id":2,"result":{}}',
            b'{"jsonrpc":"2.0","id":2,"error":{"message":"secret"}}',
            envelope({"isError": True, "structuredContent": {"ok": True}}),
            envelope({"structuredContent": {"number": float("nan")}}),
        ]:
            with self.subTest(raw=raw), self.assertRaises(ProviderFailure) as caught:
                self.run_call(Response(raw))
            self.assertNotIn("secret", str(caught.exception))
        with self.assertRaises(ProviderFailure):
            self.run_call(Response(envelope({})), Response(envelope({"protocolVersion": "wrong"}, 1)))

    def test_http_errors_redacted_and_no_redirect_handler(self) -> None:
        for status, expected in [(401, "PERMISSION_REQUIRED"), (429, "RATE_LIMITED"), (302, "PROVIDER_ERROR")]:
            with patch.object(transport, "build_opener") as build:
                build.return_value.open.side_effect = HTTPError(
                    transport.ENDPOINT, status, "private-token", Message(), None
                )
                with self.assertRaises(ProviderFailure) as caught:
                    transport.call_tool("synthetic-token", "get_project_context", {})
                self.assertEqual(caught.exception.code, expected)
                self.assertNotIn("private-token", str(caught.exception))
                self.assertEqual(build.return_value.open.call_count, 1)
                self.assertIsInstance(build.call_args.args[0], NoRedirect)


if __name__ == "__main__":
    unittest.main()
