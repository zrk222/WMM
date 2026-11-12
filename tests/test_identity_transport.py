"""Offline transport boundaries for fixed GitHub identity reads."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import json
import ssl
import sys
from types import SimpleNamespace
import tempfile
import threading
import textwrap
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
import unittest
from unittest.mock import Mock, patch

from mission_control import operator_identity
from mission_control.common import Invalid
from mission_control.providers import NoRedirect


SYNTHETIC_TOKEN = "synthetic_GITHUB_token_1234567890"
# Test-only synthetic self-signed loopback fixture; these DER bytes are not an
# application credential or a key for any account or service.
UNTRUSTED_EC_KEY_DER_BASE64 = """MHcCAQEEIAgqO7GDcAHl9Ket3y0RYiFvrorQ8lXVreeXUsXrUPycoAoGCCqGSM49
AwEHoUQDQgAED2t+q16jwDC2aV9F0WlTrXxAODVEEPzhv000qWQ4ybUNLZ0CCBxh
FtBMmp+h3RBQDkpz9hgOrvVZrb4z0HvFzg=="""
UNTRUSTED_CERT_DER_BASE64 = """MIIBRjCB7qADAgECAhQW7ylWN6owKaCXnPyHC6qT3hJonjAKBggqhkjOPQQDAjAU
MRIwEAYDVQQDDAlsb2NhbGhvc3QwHhcNMjAwMTAxMDAwMDAwWhcNNDkxMjMxMjM1
OTU5WjAUMRIwEAYDVQQDDAlsb2NhbGhvc3QwWTATBgcqhkjOPQIBBggqhkjOPQMB
BwNCAAQPa36rXqPAMLZpX0XRaVOtfEA4NUQQ/OG/TTSpZDjJtQ0tnQIIHGEW0Eya
n6HdEFAOSnP2GA6u9VmtvjPQe8XOox4wHDAaBgNVHREEEzARgglsb2NhbGhvc3SH
BH8AAAEwCgYIKoZIzj0EAwIDRwAwRAIgHStovoFgdL8iWUUmfndg5NlbgH6Pme9w
0ZIzMvn8MC8CIG+9o1HkJ62pPH8h2ftZceSFTTiRZuSa9GSvQtaSe8Ce"""


def pem_fixture(label, encoded_der):
    """Serialize the public synthetic DER fixture only inside a temp folder."""
    payload = base64.b64encode(base64.b64decode(encoded_der)).decode("ascii")
    body = "\n".join(textwrap.wrap(payload, 64))
    return "\n".join(("-----BEGIN " + label + "-----", body, "-----END " + label + "-----", ""))


class Response:
    def __init__(self, raw):
        self.raw = raw
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        self.read_sizes.append(size)
        return self.raw[:size] if size >= 0 else self.raw


class FakeOpener:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request, timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class IdentityTransportTests(unittest.TestCase):
    def reader(self, result):
        response = result if isinstance(result, Exception) else Response(result)
        opener = FakeOpener(response)
        with patch.object(operator_identity, "build_opener", return_value=opener) as builder:
            value = operator_identity.github_read("/user", SYNTHETIC_TOKEN)
        return value, opener, builder, response

    def test_fixed_reader_uses_verified_tls_and_bounded_identity_contract(self):
        payload = json.dumps({"type": "User", "id": 314159, "login": "synthetic-owner"}).encode()
        value, opener, builder, response = self.reader(payload)

        self.assertEqual(value["principal"], "github:314159")
        self.assertEqual(value["provider"], "GITHUB")
        self.assertEqual(response.read_sizes, [65537])
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + SYNTHETIC_TOKEN)
        self.assertEqual(request.get_header("X-github-api-version"), "2026-03-10")
        self.assertEqual(timeout, 15)

        handlers = builder.call_args.args
        self.assertTrue(any(isinstance(handler, NoRedirect) for handler in handlers))
        https = next(handler for handler in handlers if isinstance(handler, HTTPSHandler))
        context = https._context
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        redirect = next(handler for handler in handlers if isinstance(handler, NoRedirect))
        with self.assertRaisesRegex(Invalid, "redirect blocked"):
            redirect.redirect_request(request, None, 302, "redirect", {}, "https://evil.example/")

    def test_reader_rejects_unlisted_endpoints_before_transport(self):
        with patch.object(operator_identity, "build_opener") as builder:
            for path in ("/user?x=1", "/user/", "//evil.example/user", "/users/a/b"):
                with self.subTest(path=path), self.assertRaisesRegex(Invalid, "Unapproved identity endpoint"):
                    operator_identity.github_read(path, SYNTHETIC_TOKEN)
            builder.assert_not_called()

    def test_failed_identity_transport_does_not_admit_session(self):
        identities = operator_identity.Identities()
        with patch.object(operator_identity, "github_read", side_effect=Invalid("synthetic transport failure")):
            with self.assertRaisesRegex(Invalid, "synthetic transport failure"):
                identities.login("synthetic-session", {"token": SYNTHETIC_TOKEN})
        self.assertEqual(identities.sessions, {})

    def test_status_and_oversize_responses_are_closed(self):
        error = HTTPError("https://api.github.com/user", 401, "unauthorized", {}, None)
        opener = FakeOpener(error)
        with patch.object(operator_identity, "build_opener", return_value=opener):
            with self.assertRaisesRegex(Invalid, "HTTP 401"):
                operator_identity.github_read("/user", SYNTHETIC_TOKEN)

        opener = FakeOpener(URLError(SYNTHETIC_TOKEN))
        with patch.object(operator_identity, "build_opener", return_value=opener):
            with self.assertRaisesRegex(Invalid, "verification is unavailable") as caught:
                operator_identity.github_read("/user", SYNTHETIC_TOKEN)
        self.assertNotIn(SYNTHETIC_TOKEN, str(caught.exception))

        oversized = b"x" * 65537
        response = Response(oversized)
        opener = FakeOpener(response)
        with patch.object(operator_identity, "build_opener", return_value=opener):
            with self.assertRaisesRegex(Invalid, "response exceeds"):
                operator_identity.github_read("/user", SYNTHETIC_TOKEN)
        self.assertEqual(response.read_sizes, [65537])

    def test_existing_tls_trust_rejects_untrusted_loopback_certificate(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"not trusted")

            def log_message(self, *_):
                pass

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cert_path, key_path = root / "untrusted.pem", root / "untrusted.key"
            cert_path.write_text(pem_fixture("CERTIFICATE", UNTRUSTED_CERT_DER_BASE64), encoding="ascii")
            key_path.write_text(pem_fixture("EC PRIVATE KEY", UNTRUSTED_EC_KEY_DER_BASE64), encoding="ascii")
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.daemon_threads = True
            server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
            server.socket = server_context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"https://127.0.0.1:{server.server_port}/user"
                contexts = (operator_identity._identity_trust_context(),)
                for context in contexts:
                    with self.subTest(context=context):
                        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                        self.assertTrue(context.check_hostname)
                        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
                        opener = build_opener(
                            ProxyHandler({}),
                            NoRedirect(),
                            HTTPSHandler(context=context),
                        )
                        with self.assertRaises(URLError) as caught:
                            opener.open(Request(url), timeout=2)
                        self.assertIsInstance(caught.exception.reason, ssl.SSLCertVerificationError)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

    def test_windows_uses_explicit_native_context_without_global_injection(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        native = SimpleNamespace(SSLContext=Mock(return_value=context), inject_into_ssl=Mock())
        original_context_class = ssl.SSLContext
        with (
            patch.object(operator_identity.sys, "platform", "win32"),
            patch.dict(sys.modules, {"truststore": native}),
            patch.object(operator_identity.ssl, "create_default_context") as default,
        ):
            actual = operator_identity._identity_trust_context()
        native.SSLContext.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        native.inject_into_ssl.assert_not_called()
        default.assert_not_called()
        self.assertIs(actual, context)
        self.assertIs(ssl.SSLContext, original_context_class)
        self.assertEqual(actual.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(actual.check_hostname)
        self.assertEqual(actual.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_non_windows_uses_stdlib_without_native_dependency(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with (
            patch.object(operator_identity.sys, "platform", "linux"),
            patch.dict(sys.modules, {"truststore": None}),
            patch.object(operator_identity.ssl, "create_default_context", return_value=context) as default,
        ):
            actual = operator_identity._identity_trust_context()
        default.assert_called_once_with()
        self.assertIs(actual, context)
        self.assertEqual(actual.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(actual.check_hostname)
        self.assertEqual(actual.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_missing_windows_native_dependency_fails_before_transport(self):
        with (
            patch.object(operator_identity.sys, "platform", "win32"),
            patch.dict(sys.modules, {"truststore": None}),
            patch.object(operator_identity.ssl, "create_default_context") as default,
            patch.object(operator_identity, "build_opener") as builder,
        ):
            with self.assertRaisesRegex(Invalid, "requires the bundled native trust provider"):
                operator_identity.github_read("/user", SYNTHETIC_TOKEN)
        default.assert_not_called()
        builder.assert_not_called()

    def test_transport_failures_do_not_retry_or_downgrade(self):
        failures = (
            URLError(ssl.SSLCertVerificationError(1, "synthetic native rejection")),
            ssl.SSLCertVerificationError(1, "synthetic native revocation rejection"),
            HTTPError("https://api.github.com/user", 401, "synthetic", {}, None),
            HTTPError("https://api.github.com/user", 403, "synthetic", {}, None),
            HTTPError("https://api.github.com/user", 302, "synthetic redirect", {}, None),
            URLError(OSError("synthetic network failure")),
            ssl.SSLError("synthetic TLS protocol failure"),
            TimeoutError("synthetic timeout"),
            Invalid("Provider redirect blocked"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                opener = FakeOpener(failure)
                with (
                    patch.object(operator_identity, "build_opener", return_value=opener) as builder,
                    patch.object(operator_identity.ssl, "create_default_context") as fallback,
                ):
                    with self.assertRaises(Invalid) as caught:
                        operator_identity.github_read("/user", SYNTHETIC_TOKEN)
                self.assertEqual(builder.call_count, 1)
                self.assertEqual(len(opener.calls), 1)
                if sys.platform == "win32":
                    fallback.assert_not_called()
                self.assertNotIn(SYNTHETIC_TOKEN, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
