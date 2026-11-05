import base64
import json
import time
import unittest
from unittest.mock import patch, MagicMock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from mission_control.hosted_oidc import (OIDCClient, OIDCError, ProviderConfig, ProviderTransport,
    dependencies_available, jwt_part, jwt_parts, key_for, text_field, validate_claims)


def config():
    return ProviderConfig("https://issuer.example/", "https://issuer.example/authorize", "https://issuer.example/token", "https://issuer.example/keys", "client")


class Fixture:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.claims = {"iss": config().issuer, "sub": "subject", "aud": "client", "exp": 1100, "iat": 999, "nonce": "nonce"}
        self.jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwk.update(kid="key", use="sig", alg="RS256")
        self.deadlines = []

    def request(self, url, method, body, deadline):
        self.deadlines.append(deadline)
        if method == "POST":
            token = jwt.encode(self.claims, self.key, algorithm="RS256", headers={"kid": "key"})
            return json.dumps({"id_token": token}).encode()
        return json.dumps({"keys": [self.jwk]}).encode()


class OIDCTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.client = OIDCClient(config(), self.fixture, clock=lambda: 1000)

    def exchange(self):
        return self.client.exchange("code", "verifier", "nonce", "http://127.0.0.1:8000/auth/callback")

    def test_text_field_limits_and_control_characters(self):
        self.assertTrue(text_field("name", 4))
        for value in ("", "a\nb", "12345", 12, None):
            self.assertFalse(text_field(value, 4))

    def test_dependencies_available_missing_library_fails_closed(self):
        self.assertTrue(dependencies_available())
        with patch.dict("sys.modules", {"jwt": None}):
            self.assertFalse(dependencies_available())

    def test_jwt_part_rejects_duplicate_json_and_invalid_encoding(self):
        encode = lambda raw: base64.urlsafe_b64encode(raw).decode().rstrip("=")
        self.assertEqual(jwt_part(encode(b'{"alg":"RS256"}'))["alg"], "RS256")
        for part in ("bad!", encode(b'{"a":1,"a":2}'), encode(b"[]")):
            with self.subTest(part=part), self.assertRaises(OIDCError): jwt_part(part)

    def test_jwt_parts_rejects_bad_structure(self):
        token = jwt.encode(self.fixture.claims, self.fixture.key, algorithm="RS256", headers={"kid":"key"})
        header, claims = jwt_parts(token)
        self.assertEqual((header["kid"], claims["sub"]), ("key", "subject"))
        for value in ("a.b", "a.b.*", None):
            with self.subTest(value=value), self.assertRaises(OIDCError): jwt_parts(value)

    def test_key_for_duplicate_unknown_and_private_keys(self):
        jwk = self.fixture.jwk
        self.assertEqual(key_for({"keys":[jwk]}, "key"), jwk)
        for keys, kid in (([jwk, jwk], "key"), ([jwk], "missing"), ([dict(jwk, d="private")], "key")):
            with self.assertRaises(OIDCError): key_for({"keys":keys}, kid)

    def test_validate_claims_exact_temporal_boundary_and_multiple_audiences(self):
        claims = dict(self.fixture.claims, aud=["client", "second"], azp="client", nbf=1000, iat=1005)
        self.assertEqual(validate_claims(claims, config(), "nonce", 1000).not_before, 1000)
        claims["exp"] = 1000
        with self.assertRaises(OIDCError): validate_claims(claims, config(), "nonce", 1000)

    def test_real_signature_and_shared_deadline(self):
        self.assertEqual(self.exchange().subject, "subject")
        self.assertEqual(self.fixture.deadlines[0], self.fixture.deadlines[1])

    def test_claim_rejections(self):
        bad = [("exp", 1000), ("iat", 1006), ("iat", True), ("nbf", 1001), ("nonce", "other"), ("iss", "https://other.example/"), ("sub", ""), ("aud", "other"), ("azp", "other")]
        for key, value in bad:
            with self.subTest(key=key, value=value):
                old = self.fixture.claims.copy(); self.fixture.claims[key] = value
                with self.assertRaises(OIDCError): self.exchange()
                self.fixture.claims = old
        self.fixture.claims["aud"] = ["client", "other"]
        with self.assertRaises(OIDCError): self.exchange()
        self.fixture.claims["azp"] = "client"
        self.assertEqual(self.exchange().subject, "subject")

    def test_key_rejections(self):
        for key, value in (("kid", "other"), ("kty", "oct"), ("use", "enc"), ("d", "private"), ("alg", "HS256")):
            with self.subTest(key=key):
                original = self.fixture.jwk.copy(); self.fixture.jwk[key] = value
                with self.assertRaises(OIDCError): self.exchange()
                self.fixture.jwk = original

    def test_duplicate_json_and_signature_tamper(self):
        original = self.fixture.request
        def request(url, method, body, deadline):
            if method == "GET": return b'{"keys":[],"keys":[]}'
            return original(url, method, body, deadline)
        self.fixture.request = request
        with self.assertRaises(OIDCError): self.exchange()
        token = jwt.encode(self.fixture.claims, self.fixture.key, algorithm="RS256", headers={"kid":"key"})
        parts = token.split("."); parts[1] = base64.urlsafe_b64encode(b'{"sub":"tampered"}').decode().rstrip("=")
        self.fixture.request = lambda url, method, body, deadline: json.dumps({"id_token":".".join(parts)} if method == "POST" else {"keys":[self.fixture.jwk]}).encode()
        with self.assertRaises(OIDCError): self.exchange()

    def test_redirect_is_not_followed(self):
        conn = MagicMock(); conn.getresponse.return_value.status = 302
        with patch("mission_control.aeo_transport.address", return_value="93.184.216.34"), patch("mission_control.aeo_transport.trust_context"), patch("mission_control.aeo_transport.PinnedHTTPS", return_value=conn):
            with self.assertRaises(OIDCError): ProviderTransport().request(config().jwks_uri, "GET", None, time.monotonic()+1)
        conn.close.assert_called_once()

    def test_more_claim_types_and_missing_required_fields(self):
        mutations = [("exp", None), ("exp", float("nan")), ("iat", "1000"), ("nbf", None),
                     ("azp", None), ("sub", 3), ("aud", ["client", 3]), ("nonce", None)]
        for key, value in mutations:
            old = self.fixture.claims.copy(); self.fixture.claims[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(OIDCError): self.exchange()
            self.fixture.claims = old
        for key in ("iss", "sub", "aud", "exp", "iat", "nonce"):
            old = self.fixture.claims.copy(); del self.fixture.claims[key]
            with self.subTest(missing=key), self.assertRaises(OIDCError): self.exchange()
            self.fixture.claims = old

    def test_header_and_jwks_attacks(self):
        def reject_token(token, keys=None):
            self.fixture.request = lambda url, method, body, deadline: json.dumps({"id_token":token} if method == "POST" else {"keys":keys or [self.fixture.jwk]}).encode()
            with self.assertRaises(OIDCError): self.exchange()
        for header in ({"kid":"key", "crit":["exp"]}, {"kid":"key", "jku":"https://evil.example/"}, {"kid":"missing"}):
            token = jwt.encode(self.fixture.claims, self.fixture.key, algorithm="RS256", headers=header)
            reject_token(token)
        token = jwt.encode(self.fixture.claims, "symmetric", algorithm="HS256", headers={"kid":"key"})
        reject_token(token)
        token = jwt.encode(self.fixture.claims, self.fixture.key, algorithm="RS256", headers={"kid":"key"})
        reject_token(token, [self.fixture.jwk, self.fixture.jwk])
        for change in ({"key_ops":["sign"]}, {"x5u":"https://evil.example/"}, {"p":"secret"}):
            jwk = dict(self.fixture.jwk, **change)
            reject_token(token, [jwk])
        small = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(small.public_key())); jwk["kid"] = "key"
        reject_token(token, [jwk])

    def test_duplicate_payload_json_rejected_before_signature(self):
        header = base64.urlsafe_b64encode(b'{"alg":"RS256","kid":"key"}').decode().rstrip("=")
        payload = base64.urlsafe_b64encode(b'{"sub":"one","sub":"two"}').decode().rstrip("=")
        self.fixture.request = lambda *args: json.dumps({"id_token":header+"."+payload+".AA"}).encode()
        with self.assertRaises(OIDCError): self.exchange()

    def test_transport_request_shape_and_failure_redaction(self):
        conn = MagicMock(); response = conn.getresponse.return_value; response.status = 200
        response.getheaders.return_value = [("Content-Length", "2")]
        response.read1.side_effect = [b"{}", b""]
        with patch("mission_control.aeo_transport.address", return_value="93.184.216.34"), patch("mission_control.aeo_transport.trust_context"), patch("mission_control.aeo_transport.PinnedHTTPS", return_value=conn):
            self.assertEqual(ProviderTransport().request(config().token_endpoint, "POST", b"secret", time.monotonic()+1), b"{}")
        args, kwargs = conn.request.call_args
        self.assertEqual(args[:2], ("POST", "/token")); self.assertEqual(kwargs["body"], b"secret")
        self.assertEqual(kwargs["headers"]["Accept-Encoding"], "identity")
        self.assertNotIn("Cookie", kwargs["headers"]); conn.close.assert_called_once()
        with patch("mission_control.aeo_transport.address", side_effect=ValueError("private-secret")):
            with self.assertRaises(OIDCError) as failure: ProviderTransport().request(config().jwks_uri, "GET", None, time.monotonic()-1)
        self.assertNotIn("private-secret", str(failure.exception))


if __name__ == "__main__": unittest.main()
