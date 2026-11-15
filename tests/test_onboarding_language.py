"""Buyer onboarding stays plain and maintainer release steps stay out of it."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIRST_RUN = (ROOT / "docs/desktop-first-run.md").read_text(encoding="utf-8")
HANDOFF = (ROOT / "docs/release-handoff.md").read_text(encoding="utf-8")
README_FRONT = "\n".join((ROOT / "README.md").read_text(encoding="utf-8").splitlines()[:40])
JARGON = (
    "Hypit",
    "owner grant",
    "operation catalog",
    "Grok Bot",
    "Instinct",
    "Hark Pro",
    "Meta Muse",
    "Codex/Dots",
    "Claude Duet",
    "MCP",
)


class OnboardingLanguageTests(unittest.TestCase):
    def test_first_run_guide_uses_plain_language_and_defines_a_grant(self):
        for term in JARGON:
            with self.subTest(term=term):
                self.assertNotIn(term, FIRST_RUN)
        self.assertIn("Permission slip (also called a grant)", FIRST_RUN)
        self.assertIn("does not yet establish growth", FIRST_RUN)
        self.assertIn("Default ad spending is zero", FIRST_RUN)

    def test_readme_opening_uses_plain_language_before_the_detail_tables(self):
        for term in ("Autonomous Growth Operations Engine", "owner grant", "operation catalog", "Hypit"):
            with self.subTest(term=term):
                self.assertNotIn(term, README_FRONT)
        self.assertIn("permission slip", README_FRONT)
        self.assertIn("nothing publishes or spends on its own", README_FRONT)

    def test_release_steps_live_only_in_the_maintainer_guide(self):
        for phrase in ("Desktop public prerelease", "SHA256SUMS.txt", "draft prerelease"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, FIRST_RUN)
                self.assertIn(phrase, HANDOFF)
        self.assertIn("release-handoff.md", FIRST_RUN)


if __name__ == "__main__":
    unittest.main()
