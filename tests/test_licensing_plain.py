"""Licensing and commercial path stay plain, linkable and free of invented prices."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PRICING = " ".join((ROOT / "docs/pricing.md").read_text(encoding="utf-8").split())
LICENSING = " ".join((ROOT / "docs/licensing.md").read_text(encoding="utf-8").split())
README = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())


class LicensingLanguageTests(unittest.TestCase):
    def test_pricing_states_free_use_and_the_commercial_path(self):
        for phrase in (
            "Free — no payment",
            "internal business use",
            "paid written agreement",
            "Do not post credentials",
            "no automatic checkout",
            "no published list price yet",
            "Nothing here is legal advice",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, PRICING)
        self.assertIn("licensing.md", PRICING)

    def test_license_position_is_answered_in_plain_questions(self):
        for phrase in (
            "Can I use WMM for my own app",
            "Yes, free.",
            "Can I host it for other organizations",
            "source-available",
            "Prior Apache 2.0 grants are preserved",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, LICENSING)
        self.assertIn("pricing.md", LICENSING)

    def test_readme_links_pricing_without_claiming_growth(self):
        self.assertIn("docs/pricing.md", README)
        self.assertIn("growth and time savings are not yet established", README)


if __name__ == "__main__":
    unittest.main()
