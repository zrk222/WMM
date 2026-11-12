"""The real local server serves the named app-sales UI and no alternate paths."""

import re
import unittest
from mission_control.operator_client import ClientError
from tests import test_agent_grants as grants


class FunnelUIHTTPTests(unittest.TestCase):
    setUp = grants.GrantTests.setUp
    tearDown = grants.GrantTests.tearDown

    def test_named_ui_modules_are_served_and_shell_load_order_is_explicit(self):
        with self.owner.opener.open(self.origin + "/") as response:
            html = response.read().decode()
        self.assertEqual(re.findall(r'<script\b[^>]*src="([^"]+)"', html), ["/dashboard.mjs"])
        self.assertIn('type="module" src="/dashboard.mjs"', html)
        with self.owner.opener.open(self.origin + "/feature-apis.mjs") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("text/javascript", response.headers["Content-Type"])
            imports = re.findall(r"^import ['\"]([^'\"]+)['\"];", response.read().decode(), re.M)
        self.assertLess(imports.index("./funnel-model.js"), imports.index("./funnel-ui.js"))
        for path in ("/funnel-model.js", "/funnel-ui.js"):
            with self.owner.opener.open(self.origin + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("text/javascript", response.headers["Content-Type"])
                self.assertIn("app-sales", response.read().decode().lower())
        with self.assertRaises(ClientError):
            self.owner.request("GET", "/funnel-ui.js/extra")
