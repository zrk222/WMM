"""Deterministic property-style tests for pure parsers used by security paths."""

import base64
import json
import math
import random
import unittest
from datetime import datetime, timedelta, timezone

from mission_control.agent_grants import token_digest
from mission_control.authority_expiry import deadline
from mission_control.common import Invalid, amount, canonical, fraction, identifier, iso_time
from mission_control.payment_signature import strict_json
from mission_control.server import media_range
from mission_control.storekit_jws import certificate, url_decode

RANDOM = random.Random(20261112)


def value(depth=0):
    """Build a finite JSON value; paths stay small so failures remain readable."""
    if depth > 3:
        return RANDOM.choice([None, True, False, RANDOM.randint(-1000, 1000), "text"])
    kind = RANDOM.randrange(7)
    if kind == 0:
        return RANDOM.choice([None, True, False])
    if kind == 1:
        return RANDOM.randint(-(10**6), 10**6)
    if kind == 2:
        return RANDOM.choice([0.0, -1.5, 3.25, 1e-9])
    if kind == 3:
        return "".join(RANDOM.choice('ab"\\\n\u00e9 ') for _ in range(RANDOM.randrange(12)))
    if kind == 4:
        return [value(depth + 1) for _ in range(RANDOM.randrange(4))]
    return {f"k{RANDOM.randrange(6)}": value(depth + 1) for _ in range(RANDOM.randrange(4))}


class MediaRangeProperties(unittest.TestCase):
    def test_parsed_range_is_always_bounded(self):
        for _ in range(500):
            size = RANDOM.randint(1, 10**6)
            kind = RANDOM.randrange(3)
            if kind == 0:
                start = RANDOM.randint(0, size - 1)
                end = RANDOM.randint(start, size + 50)
                header = f"bytes={start}-{end}"
            elif kind == 1:
                start = RANDOM.randint(0, size - 1)
                header = f"bytes={start}-"
            else:
                header = f"bytes=-{RANDOM.randint(1, size + 50)}"
            begin, finish = media_range(header, size)
            self.assertGreaterEqual(begin, 0, header)
            self.assertLessEqual(begin, finish, header)
            self.assertLess(finish, size, header)
            self.assertLessEqual(finish - begin + 1, size, header)

    def test_invalid_and_unsatisfiable_headers_raise(self):
        cases = [
            "bytes=",
            "bytes=-",
            "bytes=--1",
            "bytes=1-2-3",
            "bytes= 1-2",
            "1-2",
            "bytes=+1-2",
            "bytes=1 -2",
            "bytes=-0",
            "bytes=0-0 ",
            "items=0-1",
        ]
        for header in cases:
            with self.assertRaises(Invalid, msg=header):
                media_range(header, 10)
        self.assertEqual(media_range("bytes=0-0", 10), (0, 0))
        self.assertEqual(media_range("bytes=-20", 10), (0, 9))
        with self.assertRaises(Invalid):
            media_range("bytes=5-2", 10)
        with self.assertRaises(Invalid):
            media_range("bytes=10-", 10)

    def test_zero_length_file_rejects_every_range(self):
        for header in ("bytes=-1", "bytes=0-", "bytes=0-0"):
            with self.assertRaises(Invalid, msg=header):
                media_range(header, 0)


class CanonicalProperties(unittest.TestCase):
    def test_round_trip_is_idempotent_and_key_order_independent(self):
        for _ in range(300):
            item = value()
            text = canonical(item)
            self.assertEqual(canonical(json.loads(text)), text)
            if isinstance(item, dict):
                shuffled = dict(reversed(list(item.items())))
                self.assertEqual(canonical(shuffled), text)

    def test_non_finite_numbers_and_unknown_values_are_rejected(self):
        for item in (math.nan, math.inf, -math.inf, object()):
            with self.assertRaises((ValueError, TypeError)):
                canonical(item)


class CommonInputProperties(unittest.TestCase):
    def test_identifier_accepts_only_portable_namespaces(self):
        alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
        for _ in range(200):
            parts = [
                "".join(RANDOM.choice(alphabet) for _ in range(RANDOM.randint(1, 8)))
                for _ in range(RANDOM.randint(1, 4))
            ]
            value = "-".join(parts)
            if len(value) > 60:
                continue
            self.assertEqual(identifier(value), value)
        for value in ("UPPER", "-lead", "trail-", "double--hyphen", "a/b", "a b", "", "a" * 61, "caf\u00e9"):
            with self.assertRaises(Invalid, msg=value):
                identifier(value)

    def test_amount_rejects_non_integral_and_negative_values(self):
        for _ in range(200):
            value = RANDOM.randint(0, 10**12)
            self.assertEqual(amount(value, "Amount"), value)
        for value in (-1, 1.0, True, "1", None, [], {}):
            with self.assertRaises(Invalid):
                amount(value, "Amount")

    def test_fraction_is_finite_and_closed(self):
        for _ in range(200):
            value = RANDOM.uniform(0, 1)
            self.assertEqual(fraction(value, "Fraction"), value)
        for value in (-0.001, 1.001, math.nan, math.inf, -math.inf, True, "0.5", None):
            with self.assertRaises(Invalid):
                fraction(value, "Fraction")
        self.assertEqual(fraction(0, "Fraction"), 0)
        self.assertEqual(fraction(1, "Fraction"), 1)

    def test_iso_time_requires_timezone_and_round_trips(self):
        for _ in range(200):
            stamp = datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(
                seconds=RANDOM.randint(0, 400_000_000), microseconds=RANDOM.randint(0, 999_999)
            )
            self.assertEqual(iso_time(stamp.isoformat()), stamp)
            self.assertEqual(iso_time(stamp.isoformat().replace("+00:00", "Z")), stamp)
        for value in ("2026-01-01T00:00:00", "not-a-time", "", None):
            with self.assertRaises(Invalid):
                iso_time(value)


class AuthorityDeadlineProperties(unittest.TestCase):
    def test_deadline_consent_boundary(self):
        observed = datetime(2026, 11, 12, tzinfo=timezone.utc)
        for _ in range(200):
            seconds = RANDOM.randint(1, 24 * 60 * 60)
            stamp = observed + timedelta(seconds=seconds)
            self.assertEqual(deadline(stamp.isoformat(), observed), stamp)
        for seconds in (24 * 60 * 60 + 1, 25 * 60 * 60):
            stamp = observed + timedelta(seconds=seconds)
            with self.assertRaises(Invalid):
                deadline(stamp.isoformat(), observed)
            self.assertEqual(deadline(stamp.isoformat(), observed, consent=True), stamp)
        for seconds in (-10, 0):
            with self.assertRaises(Invalid):
                deadline((observed + timedelta(seconds=seconds)).isoformat(), observed, consent=True)
        with self.assertRaises(Invalid):
            deadline("2026-11-12T00:00:00", observed, consent=True)


class GrantTokenProperties(unittest.TestCase):
    def test_grant_token_digest_is_stable_and_format_bound(self):
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        seen = set()
        for _ in range(50):
            token = "wmmg_" + "".join(RANDOM.choice(alphabet) for _ in range(43))
            digest = token_digest(token)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            self.assertEqual(token_digest(token), digest)
            self.assertNotIn(digest, seen)
            seen.add(digest)
        for token in ("wmmg_" + "a" * 42, "wmmg_" + "a" * 44, "xmmg_" + "a" * 43, "wmmg_" + "a" * 42 + "!", "", None):
            with self.assertRaises(PermissionError):
                token_digest(token)


class Base64UrlProperties(unittest.TestCase):
    def test_canonical_urlsafe_round_trip_and_cap(self):
        for _ in range(200):
            raw = bytes(RANDOM.randrange(256) for _ in range(RANDOM.randint(1, 128)))
            value = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            self.assertEqual(url_decode(value, len(raw)), raw)
            self.assertEqual(url_decode(value, len(raw) + 10), raw)
            with self.assertRaises(Invalid):
                url_decode(value, len(raw) - 1)
        for value in ("", "YQ==", "Y Q", "a+b", "a/b", "=", "abcd!", "\u00e9"):
            with self.assertRaises(Invalid, msg=value):
                url_decode(value, 100)

    def test_standard_base64_certificate_round_trip_and_bounds(self):
        for _ in range(100):
            raw = bytes(RANDOM.randrange(256) for _ in range(RANDOM.randint(1, 512)))
            value = base64.b64encode(raw).decode()
            self.assertEqual(certificate(value), raw)
        for value in ("", "YQ", "YQ=", "YQ==\n", "a+/", "\u00e9", "A" * 10925):
            with self.assertRaises(Invalid, msg=value[:16]):
                certificate(value)


class StrictJSONProperties(unittest.TestCase):
    def test_random_objects_round_trip(self):
        for _ in range(200):
            item = {f"k{index}": value() for index in range(RANDOM.randint(1, 4))}
            self.assertEqual(strict_json(json.dumps(item).encode()), item)

    def test_ambiguous_unbounded_or_nonobject_payloads_are_rejected(self):
        cases = [
            b'{"a":1,"a":2}',
            b"[1,2]",
            b'{"a":NaN}',
            b'{"a":Infinity}',
            b"",
            b" ",
            b'"text"',
            b'{"a":' + b"1" * 300000 + b"}",
        ]
        for raw in cases:
            with self.assertRaises(Invalid):
                strict_json(raw)


if __name__ == "__main__":
    unittest.main()
