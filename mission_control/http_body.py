"""Exact local HTTP payload reads with a cumulative wall-clock budget."""

import time

from .common import Invalid
from .operator_client import strict_json


def singleton(handler, name):
    """Duplicate values cannot alter an upload or owner-bound request identity."""
    values = handler.headers.get_all(name)
    if not values or len(values) != 1:
        raise Invalid("Use exactly one " + name + " header")
    return values[0]


def json_body(handler, label="Research"):
    """One strict bounded JSON body; duplicate keys and alternate framing are rejected."""
    if singleton(handler, "Content-Type") != "application/json":
        raise Invalid("Use application/json for " + label.lower() + " input")
    if handler.headers.get_all("Transfer-Encoding") is not None:
        raise Invalid(label + " input cannot use transfer encoding")
    length = singleton(handler, "Content-Length")
    if not length.isascii() or not length.isdecimal() or not 1 <= int(length) <= 1048576:
        raise Invalid(label + " input exceeds its bounded byte limit")
    return strict_json(read_exact(handler, 1048576, label))


def read_exact(handler, limit, label):
    """A trickle sender cannot renew the five-second total body-read deadline."""
    expected = int(handler.headers["Content-Length"])
    if not 0 < expected <= limit:
        raise Invalid("Request is empty or exceeds the upload limit")
    previous = handler.connection.gettimeout()
    deadline = time.monotonic() + 5
    chunks = []
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
        handler._body_bytes_read = getattr(handler, "_body_bytes_read", 0) + count
        handler.connection.settimeout(previous)
    return b"".join(chunks)


def discard_rejected_body(handler):
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
    remaining = max(0, expected - getattr(handler, "_body_bytes_read", 0))
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
