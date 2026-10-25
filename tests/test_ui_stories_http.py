"""Exact narration asset delivery on the existing loopback-only surface."""

from pathlib import Path
from urllib.request import urlopen
import unittest
from tests import test_agent_grants as fixture


class UIStoryHTTPTests(unittest.TestCase):
    setUp = fixture.GrantTests.setUp
    tearDown = fixture.GrantTests.tearDown

    def test_exact_story_asset_and_load_order(self):
        root = Path(__file__).resolve().parents[1]
        with urlopen(self.origin + "/ui-stories.js", timeout=15) as response:
            self.assertEqual(
                response.read(),
                (root / "mission_control/static/ui-stories.js").read_bytes(),
            )
        with urlopen(self.origin, timeout=15) as response:
            html = response.read().decode()
            self.assertLess(
                html.index("/ui-stories.js"), html.index("/page-reporting.js")
            )
