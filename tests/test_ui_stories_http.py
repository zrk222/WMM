"""Exact narration asset delivery on the existing loopback-only surface."""

import re
import unittest
from pathlib import Path
from urllib.request import urlopen

from tests import test_agent_grants as fixture
from tests.dashboard_fixture import assert_dashboard_entry


class UIStoryHTTPTests(unittest.TestCase):
    origin: str

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
            assert_dashboard_entry(self, html)
        with urlopen(self.origin + "/feature-apis.mjs", timeout=15) as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            imports = re.findall(r"^import ['\"]([^'\"]+)['\"];", response.read().decode(), re.M)
            self.assertLess(imports.index("./ui-stories.js"), imports.index("./page-reporting.js"))
