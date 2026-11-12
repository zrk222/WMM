"""Per-connection tuning is bounded and never weakens synchronous durability."""

import tempfile
import unittest
from pathlib import Path

from mission_control.db import connection


class SQLiteTuningTests(unittest.TestCase):
    def test_session_applies_bounded_cache_and_keeps_full_synchronous(self):
        with tempfile.TemporaryDirectory() as folder, connection(Path(folder) / "state.sqlite") as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA cache_size").fetchone()[0], -16000)
            self.assertEqual(db.execute("PRAGMA temp_store").fetchone()[0], 2)
            self.assertGreater(db.execute("PRAGMA mmap_size").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA synchronous").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
