"""Exact delivery of the fixed human editor asset and load order."""

import re
import unittest
from pathlib import Path
from urllib.request import urlopen

from tests import test_agent_grants as fixture
from tests.dashboard_fixture import assert_dashboard_entry


class VideoEditorHTTPTests(unittest.TestCase):
    origin: str

    setUp = fixture.GrantTests.setUp
    tearDown = fixture.GrantTests.tearDown

    def test_exact_editor_asset_loads_before_shared_app(self):
        with urlopen(self.origin + "/video-editor.js", timeout=15) as response:
            self.assertEqual(
                response.read(),
                (Path(__file__).resolve().parents[1] / "mission_control/static/video-editor.js").read_bytes(),
            )
        with urlopen(self.origin, timeout=15) as response:
            text = response.read().decode()
            assert_dashboard_entry(self, text)
        with urlopen(self.origin + "/feature-apis.mjs", timeout=15) as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            imports = re.findall(r"^import ['\"]([^'\"]+)['\"];", response.read().decode(), re.M)
            self.assertEqual(imports.count("./video-editor.js"), 1)
            self.assertLess(imports.index("./authority-expiry.js"), imports.index("./video-editor.js"))
        with urlopen(self.origin + "/video-editor.css", timeout=15) as response:
            self.assertEqual(response.headers.get_content_type(), "text/css")
            self.assertEqual(
                response.read(),
                (Path(__file__).resolve().parents[1] / "mission_control/static/video-editor.css").read_bytes(),
            )
