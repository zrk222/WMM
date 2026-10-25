"""Exact delivery of the fixed human editor asset and load order."""
from pathlib import Path
from urllib.request import urlopen
import unittest
from tests import test_agent_grants as fixture


class VideoEditorHTTPTests(unittest.TestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown

    def test_exact_editor_asset_loads_before_shared_app(self):
        with urlopen(self.origin+'/video-editor.js',timeout=15) as response:
            self.assertEqual(response.read(),(Path(__file__).resolve().parents[1]/'mission_control/static/video-editor.js').read_bytes())
        with urlopen(self.origin,timeout=15) as response:
            text=response.read().decode()
            self.assertLess(text.index('/video-editor.js'),text.index('/app.js'))
        with urlopen(self.origin+'/video-editor.css',timeout=15) as response:
            self.assertEqual(response.headers.get_content_type(),'text/css')
            self.assertEqual(response.read(),(Path(__file__).resolve().parents[1]/'mission_control/static/video-editor.css').read_bytes())
