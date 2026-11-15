"""Bound rejected-input disposal; no authority or execution follows rejection."""

import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.http_body import discard_rejected_body, json_body, read_exact


class Connection:
    def __init__(self):
        self.timeout: float | None = None
        self.values: list[float | None] = []

    def gettimeout(self) -> float | None:
        return self.timeout

    def settimeout(self, value: float | None) -> None:
        self.timeout = value
        self.values.append(value)


class Request:
    def __init__(self, length: str, raw: bytes) -> None:
        self.headers = Message()
        self.headers["Content-Length"] = length
        self.connection = Connection()
        self.rfile = BytesIO(raw)
        self.close_connection = False
        self._body_bytes_read = 0


def handler(length: str = "4", raw: bytes = b"test") -> Request:
    return Request(length, raw)


class RejectionBodyTests(unittest.TestCase):
    def test_small_unread_body_discarded_and_timeout_restored(self):
        value = handler()
        discard_rejected_body(value)
        self.assertEqual(value.rfile.read(), b"")
        self.assertTrue(value.close_connection)
        self.assertIsNone(value.connection.timeout)
        self.assertTrue(all(x is None or 0 < x <= 0.05 for x in value.connection.values))

    def test_already_consumed_body_does_not_read_again(self):
        value = handler()
        self.assertEqual(read_exact(value, 10, "Synthetic"), b"test")
        with patch.object(value.rfile, "read1", side_effect=AssertionError("Read consumed input twice")):
            discard_rejected_body(value)

    def test_ambiguous_or_oversized_framing_never_drains(self):
        for length in ("-1", "abc", "1048577", "9" * 100):
            value = handler(length)
            discard_rejected_body(value)
            self.assertEqual(value.rfile.tell(), 0)
        for extra in ("Content-Length", "Transfer-Encoding"):
            value = handler()
            value.headers[extra] = "4" if extra == "Content-Length" else "chunked"
            discard_rejected_body(value)
            self.assertEqual(value.rfile.tell(), 0)

    def test_slow_sender_cannot_renew_total_budget(self):
        value = handler("100")
        with (
            patch("mission_control.http_body.time.monotonic", side_effect=[0, 0.02, 0.2]),
            patch.object(value.rfile, "read1", return_value=b"x") as read,
        ):
            discard_rejected_body(value)
            self.assertEqual(read.call_count, 1)
        self.assertIsNone(value.connection.timeout)

    def test_timeout_is_discard_only_and_never_hides_rejection(self):
        value = handler()
        with patch.object(value.rfile, "read1", side_effect=TimeoutError):
            discard_rejected_body(value)
        self.assertTrue(value.close_connection)
        self.assertIsNone(value.connection.timeout)


class StrictJSONBodyTests(unittest.TestCase):
    def test_only_single_exact_headers_and_strict_json_are_admitted(self):
        cases = (
            ("2", b"{}", (), "exactly one Content-Type"),
            ("2", b"{}", (("Content-Type", "text/plain"),), "Use application/json"),
            (
                "2",
                b"{}",
                (("Content-Type", "application/json"), ("Transfer-Encoding", "chunked")),
                "cannot use transfer encoding",
            ),
            ("2", b"{}", (("Content-Type", "application/json"), ("Content-Length", "2")), "exactly one Content-Length"),
            *(
                (length, b"{}", (("Content-Type", "application/json"),), "bounded byte limit")
                for length in ("０", "+2", "0", "1048577")
            ),
            ("13", b'{"a":1,"a":2}', (("Content-Type", "application/json"),), "Duplicate"),
        )
        for length, raw, extras, expected in cases:
            with self.subTest(length=length, extras=extras):
                value = handler(length, raw)
                for name, content in extras:
                    value.headers[name] = content
                with self.assertRaisesRegex(Invalid, expected):
                    json_body(value)

    def test_json_value_remains_untrusted_and_partial_reads_are_accounted_for(self):
        value = handler("5", b"[1,2]")
        value.headers["Content-Type"] = "application/json"
        self.assertEqual(json_body(value), [1, 2])
        self.assertEqual(value._body_bytes_read, 5)
        self.assertIsNone(value.connection.timeout)

        value = handler("4", b"x")
        with self.assertRaisesRegex(Invalid, "truncated"):
            read_exact(value, 4, "Synthetic")
        self.assertEqual(value._body_bytes_read, 1)
        self.assertTrue(value.close_connection)
        self.assertIsNone(value.connection.timeout)

    def test_invalid_limits_and_short_discard_are_safe(self):
        for length in ("0", "5"):
            value = handler(length, b"x")
            with self.assertRaisesRegex(Invalid, "upload limit"):
                read_exact(value, 4, "Synthetic")
            self.assertEqual(value.rfile.tell(), 0)
        value = handler("4", b"x")
        discard_rejected_body(value)
        self.assertTrue(value.close_connection)
        self.assertIsNone(value.connection.timeout)


if __name__ == "__main__":
    unittest.main()
