"""Bound rejected-input disposal; no authority or execution follows rejection."""

from email.message import Message
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mission_control.http_body import discard_rejected_body, read_exact


class Connection:
    def __init__(self):
        self.timeout = None
        self.values = []

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value
        self.values.append(value)


def handler(length="4", raw=b"test"):
    headers = Message()
    headers["Content-Length"] = length
    return SimpleNamespace(headers=headers, connection=Connection(), rfile=BytesIO(raw), close_connection=False)


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


if __name__ == "__main__":
    unittest.main()
