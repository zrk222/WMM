"""The WMM ASO worksheet must be truthful, non-finance and pass the real preflight."""
from pathlib import Path
import json
import re
import unittest
from mission_control.aso_validation import validate_listing

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs/WMM-ASO-AEO-WORKSHEET.md").read_text(encoding="utf-8")
BLOCKS = [json.loads(block) for block in re.findall(r"```json\n(.*?)```", DOC, flags=re.S)]


class WMMASOWorksheetTests(unittest.TestCase):
    def test_both_listings_pass_the_real_preflight(self):
        self.assertEqual(len(BLOCKS), 2)
        for value in BLOCKS:
            with self.subTest(platform=value["platform"]):
                result = validate_listing(value, "2026-11-10T00:00:00+00:00")
                self.assertEqual(result["status"], "READY_FOR_REVIEW")
                self.assertEqual(result["findings"], [])

    def test_ios_fields_respect_limits_and_do_not_repeat_across_fields(self):
        ios = next(value for value in BLOCKS if value["platform"] == "iOS")
        fields = ios["fields"]
        self.assertLessEqual(len(fields["title"]), 30)
        self.assertLessEqual(len(fields["subtitle"]), 30)
        self.assertLessEqual(len(fields["keywords"]), 100)
        self.assertNotIn(", ", fields["keywords"])
        titled = set(re.findall(r"[a-z0-9]+", (fields["title"] + " " + fields["subtitle"]).casefold()))
        keywords = set(fields["keywords"].split(","))
        self.assertFalse(titled & keywords)

    def test_worksheet_is_not_a_personal_finance_listing(self):
        lowered = DOC.casefold()
        for term in ("money manager", "expense tracker", "budget planner", "track daily expenses"):
            with self.subTest(term=term):
                self.assertNotIn(term, lowered)
        self.assertIn("no growth result is claimed", lowered)
        self.assertIn("not a personal-finance app", lowered)


if __name__ == "__main__":
    unittest.main()
