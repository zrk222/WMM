"""Serve the exact human-control module and shared operation catalog."""

from pathlib import Path
from urllib.request import urlopen
import re
import unittest
from mission_control.operation_catalog import catalog
from tests import test_agent_grants as fixture


class AgentControlUITests(unittest.TestCase):
    setUp = fixture.GrantTests.setUp
    tearDown = fixture.GrantTests.tearDown

    def test_exact_static_module_and_current_catalog(self):
        root = Path(__file__).resolve().parents[1]
        with urlopen(self.origin + "/agent-control.js", timeout=15) as response:
            self.assertEqual(response.read(), (root / "mission_control/static/agent-control.js").read_bytes())
        with urlopen(self.origin, timeout=15) as response:
            html = response.read().decode()
            self.assertEqual(re.findall(r'<script\b[^>]*src="([^"]+)"', html), ["/dashboard.mjs"])
            self.assertIn('type="module" src="/dashboard.mjs"', html)
        with urlopen(self.origin + "/feature-apis.mjs", timeout=15) as response:
            self.assertEqual(response.headers.get_content_type(), "text/javascript")
            imports = re.findall(r"^import ['\"]([^'\"]+)['\"];", response.read().decode(), re.M)
            self.assertEqual(imports.count("./agent-control.js"), 1)
            self.assertLess(imports.index("./authority-expiry.js"), imports.index("./agent-control.js"))
        discovery = self.owner.request("GET", "/api/apps/sample-one/agent-operations")
        self.assertEqual(discovery["local_catalog"], catalog())
        self.assertFalse(discovery["execution_authority"])
        self.assertNotIn("token_hash", str(discovery))
