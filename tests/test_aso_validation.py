"""Listing preflight boundaries, Unicode, stale rules and supported test surfaces."""
import copy
import unittest
import time
from unittest.mock import patch
from mission_control.common import Invalid, digest
from mission_control.aso_validation import (validate_listing, field_findings, field_observation,
    keyword_findings, surface_findings, issue, rule_findings, RULE_VERSION)


def listing(platform="iOS"):
    fields = {"title": "Useful habits", "description": "Record useful progress."}
    fields.update({"subtitle": "Remember your next step", "keywords": "habits,progress,reflection"} if platform == "iOS" else {"short_description": "Remember your next step"})
    return dict(platform=platform, locale="en-US", fields=fields, surface="MANUAL_METADATA", test_fields=["title"], rule_version=RULE_VERSION)


class AsoValidationTests(unittest.TestCase):
    def test_validate_listing_preserves_original_and_truthful_status(self):
        value = listing()
        before = copy.deepcopy(value)
        result = validate_listing(value, "2026-10-27T12:00:00+00:00")
        self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["original"], before)
        self.assertEqual(result["source_hash"], digest(before))
        self.assertFalse(result["claims_verified"])
        self.assertFalse(result["provider_approved"])
        self.assertFalse(result["external_writes"])

    def test_old_rule_profile_is_flagged_and_source_version_is_preserved(self):
        value = listing()
        value["rule_version"] = "2026-10-22.v1"
        before = copy.deepcopy(value)
        result = validate_listing(value, "2026-10-27T12:00:00+00:00")
        self.assertEqual(result["rule_version"], RULE_VERSION)
        self.assertEqual(result["source_rule_version"], "2026-10-22.v1")
        self.assertEqual(result["original"], before)
        self.assertEqual(result["source_hash"], digest(before))
        self.assertIn("RULE_REVIEW_NEEDED", [row["code"] for row in result["findings"]])

    def test_field_observation_reports_unicode_keyword_units(self):
        result = field_observation("iOS", "keywords", "界" * 34, 100)
        self.assertEqual((result["characters"], result["bytes"], result["byte_reference"]), (34, 102, 100))
        ordinary = field_observation("Android", "title", "A title", 30)
        self.assertEqual(ordinary, {"field": "title", "characters": 7, "text": "A title", "maximum_characters": 30})

    def test_field_findings_exact_boundaries_and_locale_unicode(self):
        for platform, field, limit in (("iOS", "title", 30), ("iOS", "subtitle", 30),
                                       ("iOS", "promotional_text", 170), ("Android", "title", 30),
                                       ("Android", "short_description", 80), ("Android", "description", 4000)):
            value = listing(platform)
            value["fields"][field] = "界" * limit
            observations, findings = field_findings(platform, value["fields"])
            self.assertFalse(any(f["code"] == "TOO_LONG" for f in findings))
            self.assertEqual(next(r for r in observations if r["field"] == field)["characters"], limit)
            value["fields"][field] += "界"
            self.assertTrue(any(f["code"] == "TOO_LONG" for f in field_findings(platform, value["fields"])[1]))

    def test_apple_keyword_conflicting_character_and_byte_references_show_both_counts(self):
        value = listing("iOS")
        value["fields"]["keywords"] = "界" * 33 + "a"
        observations, findings = field_findings("iOS", value["fields"])
        keyword = next(row for row in observations if row["field"] == "keywords")
        self.assertEqual((keyword["characters"], keyword["bytes"], keyword["maximum_characters"], keyword["byte_reference"]), (34, 100, 100, 100))
        self.assertFalse(any(row["code"] == "KEYWORD_BYTE_REVIEW" for row in findings))
        value["fields"]["keywords"] += "b"
        result = validate_listing(value, "2026-10-27T12:00:00+00:00")
        keyword = next(row for row in result["fields"] if row["field"] == "keywords")
        self.assertEqual((keyword["characters"], keyword["bytes"]), (35, 101))
        self.assertEqual([row["code"] for row in result["findings"]], ["KEYWORD_BYTE_REVIEW"])
        self.assertEqual(result["status"], "NEEDS_REPAIR")
        self.assertIn("100 characters", result["findings"][0]["correction"])
        self.assertIn("100 bytes", result["findings"][0]["correction"])

    def test_apple_keyword_character_limit_is_distinct_from_byte_review(self):
        value = listing("iOS")
        value["fields"]["keywords"] = "a" * 101
        result = validate_listing(value, "2026-10-27T12:00:00+00:00")
        self.assertIn("TOO_LONG", [row["code"] for row in result["findings"]])
        self.assertNotIn("KEYWORD_BYTE_REVIEW", [row["code"] for row in result["findings"]])

    def test_apple_keywords_reject_invalid_unicode_without_leaking_encoding_error(self):
        with self.assertRaisesRegex(Invalid, "valid UTF-8"):
            field_findings("iOS", {"keywords": "\ud800"})

    def test_keyword_findings_duplication_and_separator_phrases(self):
        self.assertEqual(keyword_findings({"keywords": "real estate,home"}), [])
        found = keyword_findings({"keywords": "Habit, habit,progress"})
        self.assertEqual({r["code"] for r in found}, {"DUPLICATE_KEYWORD", "SEPARATOR_SPACING"})

    def test_surface_findings_correctly_separates_metadata_from_visual_experiments(self):
        self.assertEqual(surface_findings("iOS", "PRODUCT_PAGE_OPTIMIZATION", ["screenshots", "icon"]), [])
        self.assertTrue(surface_findings("iOS", "PRODUCT_PAGE_OPTIMIZATION", ["title"]))
        self.assertEqual(surface_findings("Android", "LOCALIZED_LISTING_EXPERIMENT", ["short_description"]), [])
        self.assertTrue(surface_findings("Android", "LOCALIZED_LISTING_EXPERIMENT", ["title"]))
        self.assertTrue(surface_findings("Android", "LOCALIZED_LISTING_EXPERIMENT", ["video"]))
        self.assertTrue(surface_findings("Android", "DEFAULT_GRAPHICS_EXPERIMENT", ["description"]))
        self.assertEqual([row["code"] for row in keyword_findings({"keywords": "界" * 34})], ["KEYWORD_BYTE_REVIEW"])
        with self.assertRaises(Invalid):
            surface_findings("iOS", "PRODUCT_PAGE_OPTIMIZATION", ["icon", "icon"])

    def test_stale_rules_missing_fields_and_claim_review(self):
        self.assertTrue(rule_findings("old", "2026-10-22T12:00:00+00:00"))
        value = listing("Android")
        value["fields"]["title"] = "#1 guaranteed best app"
        value["fields"].pop("short_description")
        result = validate_listing(value, "2027-10-22T12:00:00+00:00")
        self.assertEqual({r["code"] for r in result["findings"]}, {"RULE_REVIEW_NEEDED", "MISSING", "CLAIM_REVIEW"})
        self.assertEqual(issue("title", "MISSING", "Repair")["correction"], "Repair")

    def test_malformed_inputs_and_cross_platform_fields(self):
        for key, item in (("platform", "web"), ("locale", ""), ("fields", {"subtitle": "wrong"}), ("surface", "unknown")):
            value = listing("Android")
            value[key] = item
            with self.subTest(key=key), self.assertRaises(Invalid):
                validate_listing(value, "2026-10-27T12:00:00+00:00")

    def test_bounded_local_preflight_without_network_or_mutation(self):
        value = listing("Android")
        value["fields"]["description"] = "界" * 4000
        before = copy.deepcopy(value)
        started = time.perf_counter()
        with patch("socket.socket") as network:
            for _ in range(100):
                self.assertEqual(validate_listing(value, "2026-10-27T12:00:00+00:00")["status"], "READY_FOR_REVIEW")
            network.assert_not_called()
        self.assertEqual(value, before)
        self.assertLess(time.perf_counter() - started, 5)
