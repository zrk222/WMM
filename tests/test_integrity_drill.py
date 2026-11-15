"""The local integrity drill proves integrity, restore and migration replay."""

import unittest

from mission_control.integrity_drill import run
from mission_control.migrations import BASELINE_VERSION, discovered


class IntegrityDrillTests(unittest.TestCase):
    def test_primary_backup_and_fresh_replay_agree(self):
        receipt = run()
        self.assertTrue(receipt["ok"], receipt)
        self.assertEqual(receipt["integrity_check"], ["ok"])
        self.assertEqual(receipt["foreign_key_violations"], [])
        self.assertEqual(receipt["backup"]["integrity_check"], ["ok"])
        self.assertTrue(receipt["backup"]["counts_match"])
        self.assertEqual(receipt["replay_after_backup"], [])
        expected_versions = [BASELINE_VERSION, *(version for version, _, _ in discovered())]
        self.assertEqual(receipt["migrations"], expected_versions)
        self.assertEqual(receipt["user_version"], expected_versions[-1])
        self.assertTrue(receipt["replay_digest_match"])
        self.assertGreater(receipt["table_count"], 100)


if __name__ == "__main__":
    unittest.main()
