"""The documented install batch must pass the real validator."""

from pathlib import Path
import json
import re
import unittest
from mission_control.install_attribution import validate_batch

ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = (ROOT / "docs/WIZEME-MEASUREMENT-RUNBOOK.md").read_text(encoding="utf-8")


def example():
    blocks = re.findall(r"```json\n(.*?)```", RUNBOOK, flags=re.S)
    payload = next(block for block in blocks if "source_event_count" in block)
    substitutions = {
        "<study uuid>": "11111111-1111-4111-8111-111111111111",
        "<new canonical uuid>": "22222222-2222-4222-8222-222222222222",
        "<64 lowercase hex>": "a" * 64,
        "<UTC ISO time after the window>": "2026-11-10T00:00:00+00:00",
        "<UTC study start>": "2026-11-01T00:00:00+00:00",
        "<UTC study end>": "2026-11-08T00:00:00+00:00",
        "<opaque token>": "install_a",
        "<UTC ISO time>": "2026-11-02T00:00:00+00:00",
    }
    for source, value in substitutions.items():
        payload = payload.replace(source, value)
    return json.loads(payload)


class InstallDocTests(unittest.TestCase):
    def test_documented_batch_passes_validation(self):
        value = validate_batch(example())
        self.assertEqual(value["window"]["starts_at"], "2026-11-01T00:00:00+00:00")
        self.assertEqual(value["coverage"]["source_event_count"], 1)
        self.assertEqual(value["installs"][0]["install_id"], "install_a")

    def test_runbook_points_to_the_shipped_preview_confirm_ui_first(self):
        self.assertIn("Results ? Install attribution", RUNBOOK)
        self.assertIn("Import install", RUNBOOK)
        self.assertIn("previews the coverage checklist", RUNBOOK)
        self.assertNotIn("not shipped yet", RUNBOOK)

    def test_runbook_cli_and_example_include_the_required_window(self):
        self.assertIn("--window-start", RUNBOOK)
        self.assertIn("--window-end", RUNBOOK)
        self.assertIn('"window"', RUNBOOK)


if __name__ == "__main__":
    unittest.main()
