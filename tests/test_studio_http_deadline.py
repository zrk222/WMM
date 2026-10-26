"""Interrupted HTTP parsing must retain timeout and single-send semantics on every OS."""
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from mission_control.common import Invalid
from mission_control import hypit_studio_http as target


class DeadlineTests(unittest.TestCase):
    def exchange(self, endpoint, expired, clock_expired=False, status=200):
        connection = MagicMock()
        response = MagicMock(status=status)
        response.headers.get_content_type.return_value = 'text/plain'
        clock = MagicMock(return_value=1.0)
        def entered():
            connection.expired = expired
            if clock_expired:clock.return_value = 3.0
            return response
        connection.getresponse.return_value.__enter__.side_effect = entered
        with patch.object(target, 'connection_for', return_value=connection), \
             patch.object(target.threading, 'Timer') as timer_factory, patch.object(target.time, 'monotonic', clock):
            try:
                if endpoint == 'read':target.session_bytes('http://127.0.0.1:1234', lambda:None, 2.0, 100)
                else:target.parameter_bytes('http://127.0.0.1:1234', b'{}', lambda:None, 2.0, 100)
            finally:
                connection.request.assert_called_once()
                connection.close.assert_called_once()
                timer_factory.return_value.cancel.assert_called_once()
                timer_factory.return_value.join.assert_called_once()

    def test_check_deadline_interrupted_headers_are_timeouts_before_status_or_content_type(self):
        for endpoint in ('read', 'mutation'):
            for status in (200, 503):
                with self.subTest(endpoint=endpoint, status=status), self.assertRaises(TimeoutError):
                    self.exchange(endpoint, True, status=status)

    def test_elapsed_deadline_without_watchdog_flag_also_precedes_header_validation(self):
        for endpoint in ('read', 'mutation'):
            with self.subTest(endpoint=endpoint), self.assertRaises(TimeoutError):
                self.exchange(endpoint, False, clock_expired=True)

    def test_start_watchdog_and_close_connection_preserve_protocol_error_classification(self):
        for endpoint in ('read', 'mutation'):
            with self.subTest(endpoint=endpoint), self.assertRaises(Invalid):
                self.exchange(endpoint, False)
        with self.assertRaises(HTTPError):self.exchange('read', False, status=503)

    def test_watchdog_eof_after_body_deadline_is_not_a_premature_body_error(self):
        response = MagicMock(length=12)
        with patch.object(target.time, 'monotonic', return_value=1.0) as clock:
            def interrupted_read(size):
                clock.return_value = 3.0
                return b''
            response.read1.side_effect = interrupted_read
            with self.assertRaises(TimeoutError):target.bounded_body(response, lambda:None, 2.0, 100)
