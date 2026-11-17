"""Bounded read-only OpenSEO Streamable HTTP transport; credentials stay in memory."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .common import Invalid
from .insights_transport import ProviderFailure
from .payment_signature import bounded_tree, unique_pairs
from .providers import NoRedirect

ENDPOINT = "https://app.openseo.so/mcp"
PROTOCOL = "2025-03-26"
LIMIT = 2 * 1024 * 1024
READ_TOOLS = frozenset(
    {
        "get_project_context",
        "get_search_console_performance",
        "get_google_analytics_organic_landing_pages",
        "inspect_urls",
        "get_audit_issues",
    }
)


def invalid() -> ProviderFailure:
    return ProviderFailure("INVALID_RESPONSE", "OpenSEO returned an invalid protocol response")


def decode(raw: str) -> dict:
    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs)
        bounded_tree(value)
    except (ValueError, UnicodeError, RecursionError, Invalid):
        raise invalid() from None
    if not isinstance(value, dict):
        raise invalid()
    return value


def sse_response(text: str) -> dict:
    events, lines = [], []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") + [""]:
        if not line:
            if lines:
                events.append(decode("\n".join(lines)))
                lines = []
        elif line.startswith("data:"):
            lines.append(line[5:].removeprefix(" "))
    matches = [item for item in events if "id" in item]
    if len(matches) != 1:
        raise invalid()
    return matches[0]


def response_result(raw: bytes, content_type: str, request_id: int) -> dict:
    """Accept one matching response, including bounded SSE data events."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise invalid() from None
    if content_type.split(";", 1)[0].strip().lower() == "text/event-stream":
        value = sse_response(text)
    elif content_type.split(";", 1)[0].strip().lower() == "application/json":
        value = decode(text)
    else:
        raise invalid()
    if value.get("jsonrpc") != "2.0" or type(value.get("id")) is not int or value["id"] != request_id:
        raise invalid()
    if "error" in value:
        raise ProviderFailure("PROVIDER_ERROR", "OpenSEO rejected the read request")
    if not isinstance(value.get("result"), dict):
        raise invalid()
    return value["result"]


def validate_call(token: str, tool: str, args: dict) -> None:
    if tool not in READ_TOOLS:
        raise ProviderFailure("TOOL_DENIED", "OpenSEO tool is outside the approved read scope")
    if not isinstance(token, str) or not token or len(token) > 8192 or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise ProviderFailure("PERMISSION_REQUIRED", "OpenSEO token is missing or invalid")
    if not isinstance(args, dict):
        raise ProviderFailure("INVALID_ARGUMENTS", "OpenSEO arguments must be an object")


class Client:
    def __init__(self, token: str) -> None:
        self.token = token
        self.opener = build_opener(NoRedirect())
        self.session: str | None = None

    def encode(self, method: str, params: dict | None, request_id: int | None) -> bytes:
        body: dict[str, object] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if request_id is not None:
            body["id"] = request_id
        try:
            bounded_tree(body)
            data = json.dumps(body, allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, RecursionError, Invalid):
            raise ProviderFailure("INVALID_ARGUMENTS", "OpenSEO arguments are invalid") from None
        if len(data) > LIMIT:
            raise ProviderFailure("INVALID_ARGUMENTS", "OpenSEO arguments exceed the size limit")
        return data

    def headers(self) -> dict[str, str]:
        headers = {
            "Authorization": "Bearer " + self.token,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
        }
        if self.session is not None:
            headers["Mcp-Session-Id"] = self.session
        return headers

    def exchange(self, data: bytes) -> tuple[bytes, int, str]:
        try:
            with self.opener.open(
                Request(ENDPOINT, data=data, headers=self.headers(), method="POST"),  # noqa: S310 -- constant HTTPS endpoint, NoRedirect.
                timeout=15,
            ) as response:
                raw = response.read(LIMIT + 1)
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                returned_session = response.headers.get("Mcp-Session-Id")
        except HTTPError as exc:
            code = (
                "PERMISSION_REQUIRED"
                if exc.code in (401, 403)
                else "RATE_LIMITED"
                if exc.code == 429
                else "PROVIDER_ERROR"
            )
            raise ProviderFailure(code, "OpenSEO HTTP " + str(exc.code) + "; check access and retry later") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ProviderFailure("NETWORK_ERROR", "OpenSEO read failed; retry later") from None
        if len(raw) > LIMIT:
            raise ProviderFailure("RESPONSE_TOO_LARGE", "OpenSEO response exceeds 2 MB")
        self.accept_session(returned_session)
        return raw, status, content_type

    def accept_session(self, returned_session: str | None) -> None:
        if returned_session is not None:
            if not re.fullmatch(r"[\x21-\x7e]{1,512}", returned_session) or (
                self.session is not None and returned_session != self.session
            ):
                raise invalid()
            self.session = returned_session

    def post(self, method: str, params: dict | None = None, request_id: int | None = None) -> dict:
        raw, status, content_type = self.exchange(self.encode(method, params, request_id))
        if request_id is None:
            if status != 202 or raw.strip():
                raise invalid()
            return {}
        if status != 200:
            raise invalid()
        return response_result(raw, content_type, request_id)

    def initialize(self) -> None:
        initialized = self.post(
            "initialize",
            {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "wmm", "version": "1"}},
            1,
        )
        if initialized.get("protocolVersion") != PROTOCOL:
            raise invalid()
        self.post("notifications/initialized")


def call_tool(token: str, tool: str, args: dict) -> dict:
    """Call only allowlisted reads, negotiating a fresh ephemeral MCP session."""
    validate_call(token, tool, args)
    client = Client(token)
    client.initialize()
    result = client.post("tools/call", {"name": tool, "arguments": args}, 2)
    if result.get("isError", False) is not False:
        raise ProviderFailure("PROVIDER_ERROR", "OpenSEO tool could not provide evidence")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise invalid()
    return structured
