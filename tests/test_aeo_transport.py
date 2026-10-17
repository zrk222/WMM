"""Public-read boundaries with isolated sockets/DNS and actual local CA parsing."""
from datetime import datetime, timezone
import io
import socket
import ssl
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from mission_control import aeo_tls as tls, aeo_transport as transport


def der(tag, body):
    size = len(body)
    length = bytes([size]) if size < 128 else bytes([129, size])
    return bytes([tag]) + length + body


def certificate(first=b"201001000000Z", last=b"491231235959Z"):
    validity = der(48, der(23, first) + der(23, last))
    return der(48, der(48, der(160, der(2, b"\x02")) + der(2, b"\x01") + der(48, b"") + der(48, b"") + validity))


def answer(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


def resource(url, status=200, headers=None, body=b"test"):
    return {"url": url, "status": status, "headers": headers or {}, "body": body}


class TLS(unittest.TestCase):
    def test_generalized_der_time_and_invalid_time_tag(self):
        value, end = tls.der_time(der(24, b"20500101000000Z"), 0)
        self.assertEqual(value.year, 2050); self.assertEqual(end, 17)
        with self.assertRaises(ValueError):
            tls.der_time(der(22, b"20500101000000Z"), 0)

    def test_canonical_certificate_times(self):
        first, last = tls.certificate_times(certificate())
        self.assertEqual(first.year, 2020); self.assertEqual(last.year, 2049)
        first, _ = tls.certificate_times(certificate(first=b"500101000000Z"))
        self.assertEqual(first.year, 1950)

    def test_invalid_der_and_dates_fail(self):
        for value in (b"", b"\x30\x80", b"\x30\x81\x01\x00", certificate(first=b"260231000000Z"), certificate()+b"junk"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tls.certificate_times(value)

    def test_existing_trust_only_and_required_verification(self):
        baseline = set(ssl.create_default_context().get_ca_certs(binary_form=True))
        context = tls.trust_context(); chosen = set(context.get_ca_certs(binary_form=True))
        self.assertTrue(chosen); self.assertLessEqual(chosen, baseline)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED); self.assertTrue(context.check_hostname)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        stamp = datetime.now(timezone.utc)
        for raw in chosen:
            first, last = tls.certificate_times(raw)
            self.assertLessEqual(first, stamp); self.assertGreaterEqual(last, stamp)


class URL(unittest.TestCase):
    def test_component_boundaries_without_network(self):
        self.assertEqual(transport.url_parts("https://example.com:443/page").port, 443)
        self.assertEqual(transport.hostname("EXAMPLE.COM"), "example.com")
        self.assertEqual(transport.url_path(""), "/")
        self.assertEqual(transport.url_path("/café"), "/caf%C3%A9")
        for value in ("-invalid.example", "example..com", "127.0.0.1"):
            with self.assertRaises(transport.ReadError):
                transport.hostname(value)

    def test_canonical_public_url(self):
        self.assertEqual(transport.public_url("https://Sample-One.app:443/"), "https://sample-one.app/")
        self.assertEqual(transport.public_url("https://example.com/café"), "https://example.com/caf%C3%A9")

    def test_forbidden_url_surfaces(self):
        values = [None, "http://example.com/", "https://a:b@example.com/", "https://example.com/?x=1", "https://example.com/#x", "https://example.com/?", "https://127.0.0.1/", "https://[::1]/", "https://localhost/", "https://example.com:444/", "https://example.com/\r\nX:x", "https://example.com/%0A", "https://example.com/\\private", "https://example.com/%5cprivate", "https://example.com/%zz", "https://example.com/"+"a"*2049]
        for value in values:
            with self.subTest(value=value), self.assertRaises(transport.ReadError):
                transport.public_url(value)

    def test_public_dns_only_and_mixed_answers(self):
        with patch.object(transport, "dns_lookup", return_value=answer("93.184.216.34")):
            self.assertEqual(transport.address("example.com", time.monotonic()+1), "93.184.216.34")
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "224.0.0.1", "::1", "fe80::1", "::ffff:8.8.8.8", "192.0.2.1"):
            with self.subTest(ip=ip), patch.object(transport, "dns_lookup", return_value=answer("93.184.216.34")+answer(ip)), self.assertRaises(transport.ReadError):
                transport.address("example.com", time.monotonic()+1)

    def test_dns_deadline_and_busy_are_bounded(self):
        release = threading.Event(); slots = threading.BoundedSemaphore(1)
        def slow(*args, **kwargs):
            release.wait(1); return answer("93.184.216.34")
        with patch.object(transport, "DNS_SLOTS", slots), patch.object(socket, "getaddrinfo", slow):
            start = time.monotonic()
            with self.assertRaisesRegex(transport.ReadError, "DEADLINE"):
                transport.dns_lookup("example.com", start+.02)
            with self.assertRaisesRegex(transport.ReadError, "DNS_BUSY"):
                transport.dns_lookup("example.com", time.monotonic()+1)
            self.assertLess(time.monotonic()-start, .5)
            release.set()


class Transport(unittest.TestCase):
    def test_slow_headers_and_chunk_reads_obey_total_deadline(self):
        class Slow(io.BytesIO):
            def read1(self, size):
                time.sleep(.01)
                return super().read1(min(size, 1))
        for operation in ("readline", "read"):
            start = time.monotonic()
            source = transport.DeadlineFile(Slow(b"x"*50), MagicMock(), start+.025)
            with self.subTest(operation=operation), self.assertRaisesRegex(transport.ReadError, "DEADLINE"):
                getattr(source, operation)(50)
            self.assertLess(time.monotonic()-start, .3)

    def test_standard_http_headers_and_chunked_framing_use_wrapper(self):
        sock = MagicMock()
        sock.makefile.return_value = io.BytesIO(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nhi\r\n0\r\n\r\n")
        response = transport.DeadlineResponse(sock, time.monotonic()+1)
        response.begin(); self.assertEqual(response.status, 200)
        self.assertEqual(response.read1(100), b"hi"); self.assertEqual(response.read1(100), b"")
        self.assertTrue(sock.settimeout.called)
        file = transport.DeadlineFile(io.BytesIO(b"x"*17000), MagicMock(), time.monotonic()+1)
        with self.assertRaisesRegex(transport.ReadError, "HEADERS_TOO_LARGE"):
            file.readline()

    def reader(self):
        with patch.object(transport, "trust_context", return_value=MagicMock()):
            return transport.PublicReader()

    def test_pinned_socket_keeps_original_hostname(self):
        raw = MagicMock(); context = MagicMock()
        with patch.object(socket, "create_connection", return_value=raw) as connect:
            conn = transport.PinnedHTTPS("example.com", "93.184.216.34", context, time.monotonic()+10); conn.connect()
        self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 443))
        context.wrap_socket.assert_called_once_with(raw, server_hostname="example.com")

    def test_body_length_framing_and_safe_once_failure(self):
        self.assertIsNone(transport.body_length({}, 100))
        self.assertEqual(transport.body_length({"content-length":["0"]}, 100), 0)
        for fields in ({"content-length":["5", "5"]}, {"content-length":["-1"]}):
            with self.assertRaises(transport.ReadError):
                transport.body_length(fields, 100)
        reader = self.reader(); reader.once = MagicMock(side_effect=OSError("private path"))
        with self.assertRaisesRegex(transport.ReadError, "NETWORK_FAILED"):
            reader.safe_once("https://example.com/", 100)
        self.assertEqual(reader.redirect(resource("https://example.com/dir/page", 302, {"location":["next"]}), "https://example.com"), "https://example.com/dir/next")

    def test_actual_once_wires_limits_user_agent_and_hash(self):
        response = MagicMock(); response.status = 200; response.getheaders.return_value = [("Content-Type", "text/plain")]
        response.read1.side_effect = [b"hello", b""]
        conn = MagicMock(); conn.getresponse.return_value = response
        reader = self.reader()
        with patch.object(transport, "address", return_value="93.184.216.34"), patch.object(transport, "PinnedHTTPS", return_value=conn):
            observed = reader.once("https://example.com/path", 10)
        self.assertEqual(observed["bytes"], 5); self.assertEqual(observed["sha256"], "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        self.assertEqual(conn.request.call_args.args, ("GET", "/path")); self.assertEqual(conn.request.call_args.kwargs["headers"]["Accept-Encoding"], "identity")
        self.assertEqual(conn.request.call_args.kwargs["headers"]["User-Agent"], "AppGrowthMissionControl/1.0")
        conn.close.assert_called_once()

    def test_socket_is_closed_after_tls_failure(self):
        raw = MagicMock(); context = MagicMock(); context.wrap_socket.side_effect = ssl.SSLError("private details")
        with patch.object(socket, "create_connection", return_value=raw), self.assertRaises(ssl.SSLError):
            transport.PinnedHTTPS("example.com", "93.184.216.34", context, time.monotonic()+10).connect()
        raw.close.assert_called_once()

    def test_response_caps_encodings_and_partial_bodies(self):
        conn = MagicMock()
        for headers, raw, cap, expected in [({"content-encoding":["gzip"]}, b"", 5, "ENCODING_UNSUPPORTED"), ({"content-length":["6"]}, b"", 5, "BODY_TOO_LARGE"), ({}, b"123456", 5, "BODY_TOO_LARGE"), ({"content-length":["5"]}, b"123", 5, "BODY_INCOMPLETE")]:
            with self.subTest(headers=headers, raw=raw):
                response = io.BytesIO(raw)
                with self.assertRaisesRegex(transport.ReadError, expected):
                    transport.response_body(response, headers, cap, conn, time.monotonic()+1)
        self.assertEqual(transport.response_body(io.BytesIO(b"12345"), {}, 5, conn, time.monotonic()+1), b"12345")
        self.assertTrue(conn.stream_socket.settimeout.called)

    def test_redacted_headers_and_metadata(self):
        response = MagicMock(); response.getheaders.return_value = [("Set-Cookie", "secret"), ("X-Robots-Tag", "noindex"), ("X-Robots-Tag", "nosnippet")]
        self.assertEqual(transport.response_headers(response), {"x-robots-tag":["noindex", "nosnippet"]})
        response.getheaders.return_value = [("X-Long", "x"*17000)]
        with self.assertRaisesRegex(transport.ReadError, "HEADERS_TOO_LARGE"):
            transport.response_headers(response)

    def test_redirects_remain_same_origin(self):
        reader = self.reader(); url = "https://example.com/"
        reader.once = MagicMock(side_effect=[resource(url, 302, {"location":["/next"]}), resource(url+"next")])
        self.assertEqual(reader.read(url, 1024)["status"], 200); self.assertEqual(reader.requests, 2)
        self.assertEqual(reader.once.call_args.args[0], url+"next")
        for location in ("https://evil.example/", "http://example.com/", "//127.0.0.1/"):
            reader = self.reader(); reader.once = MagicMock(return_value=resource(url, 302, {"location":[location]}))
            with self.subTest(location=location), self.assertRaises(transport.ReadError):
                reader.read(url, 1024)
            self.assertEqual(reader.once.call_count, 1)

    def test_global_request_redirect_and_deadline_limits(self):
        url = "https://example.com/"; reader = self.reader()
        reader.once = MagicMock(return_value=resource(url, 302, {"location":["/next"]}))
        with self.assertRaisesRegex(transport.ReadError, "REDIRECT_LIMIT"):
            reader.read(url, 1024)
        self.assertEqual(reader.once.call_count, 3)
        reader = self.reader(); reader.once = MagicMock(return_value=resource(url))
        for _ in range(6):
            reader.read(url, 1024)
        with self.assertRaisesRegex(transport.ReadError, "REQUEST_LIMIT"):
            reader.read(url, 1024)
        reader = self.reader(); reader.deadline = time.monotonic()-1
        with self.assertRaisesRegex(transport.ReadError, "DEADLINE"):
            reader.read(url, 1024)

    def test_redirect_target_robots_checked_before_request(self):
        url = "https://example.com/"; reader = self.reader()
        reader.once = MagicMock(return_value=resource(url, 302, {"location":["/private"]}))
        with self.assertRaisesRegex(transport.ReadError, "ROBOTS_TARGET_BLOCKED"):
            reader.read(url, 1024, permit=lambda value: not value.endswith("private"))
        self.assertEqual(reader.once.call_count, 1)

    def test_tls_error_is_classified_not_disclosed(self):
        reader = self.reader(); reader.once = MagicMock(side_effect=ssl.SSLError("private path credential"))
        with self.assertRaises(transport.ReadError) as caught:
            reader.read("https://example.com/", 1024)
        self.assertEqual(caught.exception.code, "TLS_FAILED"); self.assertNotIn("credential", str(caught.exception))

    def test_utf8_only(self):
        self.assertEqual(transport.text(resource("x", body=b"\xef\xbb\xbfhello")), "hello")
        for item in (resource("x", body=b"\xff"), resource("x", headers={"content-type":["text/html; charset=iso-8859-1"]})):
            with self.assertRaises(transport.ReadError):
                transport.text(item)


if __name__ == "__main__":
    unittest.main()
