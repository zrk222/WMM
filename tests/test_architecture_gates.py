"""Acyclic layering and catalog coverage are enforced mechanically."""

import unittest

from mission_control.architecture import check


class ArchitectureGateTests(unittest.TestCase):
    def test_no_cycles_reversed_storage_edges_or_untested_operations(self):
        self.assertEqual(check(), [])


if __name__ == "__main__":
    unittest.main()
