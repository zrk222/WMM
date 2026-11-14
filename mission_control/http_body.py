"""Exact local HTTP payload reads with a cumulative wall-clock budget."""

# pyright: strict

import time
from typing import Protocol

from .common import Invalid
from .operator_client import strict_json


class RequestHeaders(Protocol):
    def get_all(self, name: str, /) -> list[str] | None: ...

    def __getitem__(self, name: str, /) -> str: ...


class RequestConnection(Protocol):
    def gettimeout(self) -> float | None: ...

    def settimeout(self, timeout: float | None, /) -> None: ...


class RequestStream(Protocol):
    def read1(self, size: int, /) -> bytes: ...


class BodyRequest(Protocol):
    close_connection: bool

    @property
    def headers(self) -> RequestHeaders: ...

    @property
    def connection(self) -> RequestConnection: ...

    @property
    def rfile(self) -> RequestStream: ...


def _consumed(handler: BodyRequest) -> int:
    return getattr(handler, "_body_bytes_read", 0)


def singleton(handler: BodyRequest, name: str) -> str:
    """Duplicate values cannot alter an upload or owner-bound request identity."""
    values = handler.headers.get_all(name)
    if not values or len(values) != 1:
        raise Invalid("Use exactly one " + name + " header")
    return values[0]


def json_body(handler: BodyRequest, label: str = "Research") -> object:
    """One strict bounded JSON body; duplicate keys and alternate framing are rejected."""
    if singleton(handler, "Content-Type") != "application/json":
        raise Invalid("Use application/json for " + label.lower() + " input")
    if handler.headers.get_all("Transfer-Encoding") is not None:
        raise Invalid(label + " input cannot use transfer encoding")
    length = singleton(handler, "Content-Length")
    if not length.isascii() or not length.isdecimal() or not 1 <= int(length) <= 1048576:
        raise Invalid(label + " input exceeds its bounded byte limit")
    return strict_json(read_exact(handler, 1048576, label))


def read_exact(handler: BodyRequest, limit: int, label: str) -> bytes:
    """A trickle sender cannot renew the five-second total body-read deadline."""
    expected = int(handler.headers["Content-Length"])
    if not 0 < expected <= limit:
        raise Invalid("Request is empty or exceeds the upload limit")
    previous = handler.connection.gettimeout()
    deadline = time.monotonic() + 5
    chunks: list[bytes] = []
    count = 0
    try:
        while count < expected:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            handler.connection.settimeout(remaining)
            chunk = handler.rfile.read1(min(65536, expected - count))
            if time.monotonic() >= deadline:
                raise TimeoutError()
            if not chunk:
                raise Invalid(label + " request body is truncated")
            chunks.append(chunk)
            count += len(chunk)
    except (TimeoutError, OSError):
        handler.close_connection = True
        raise Invalid(label + " request body did not arrive within 5 seconds") from None
    except Invalid:
        handler.close_connection = True
        raise
    finally:
        handler.__setattr__("_body_bytes_read", _consumed(handler) + count)
        handler.connection.settimeout(previous)
    return b"".join(chunks)


def discard_rejected_body(handler: BodyRequest) -> None:
    """Bound unread small request bytes so rejection JSON survives socket close.

    Rejected input is discarded, never parsed or dispatched. Ambiguous framing,
    oversized bodies and slow senders do not enlarge this recovery budget.
    """
    values = handler.headers.get_all("Content-Length") or []
    if (
        handler.headers.get_all("Transfer-Encoding") is not None
        or len(values) != 1
        or not values[0].isascii()
        or not values[0].isdecimal()
        or len(values[0]) > 8
    ):
        return
    expected = int(values[0])
    if not 0 < expected <= 1048576:
        return
    remaining = max(0, expected - _consumed(handler))
    previous = handler.connection.gettimeout()
    deadline = time.monotonic() + 0.1
    try:
        while remaining:
            budget = deadline - time.monotonic()
            if budget <= 0:
                break
            handler.connection.settimeout(min(0.05, budget))
            raw = handler.rfile.read1(min(65536, remaining))
            if not raw:
                break
            remaining -= len(raw)
    except (OSError, TimeoutError):
        pass
    finally:
        handler.close_connection = True
        handler.connection.settimeout(previous)
