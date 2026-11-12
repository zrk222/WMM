"""The real loopback server delivers the packaging UI without widening file access."""

import re
import unittest
from tests.test_http import HTTPTests


class PackagingStaticTests(unittest.TestCase):
    setUp = HTTPTests.setUp
    tearDown = HTTPTests.tearDown
    request = HTTPTests.request

    def test_shell_loads_packaging_dependencies_in_order(self):
        code, body, headers = self.request("/")
        self.assertEqual(code, 200)
        shell = body.decode("utf-8")
        self.assertEqual(re.findall(r'<script\b[^>]*src="([^"]+)"', shell), ["/dashboard.mjs"])
        self.assertIn('type="module" src="/dashboard.mjs"', shell)
        code, adapter, response_headers = self.request("/feature-apis.mjs")
        self.assertEqual(code, 200)
        self.assertIn("text/javascript", response_headers["Content-Type"])
        imports = re.findall(r"^import ['\"]([^'\"]+)['\"];", adapter.decode(), re.M)
        self.assertLess(imports.index("./packaging-model.js"), imports.index("./packaging-ui.js"))
        self.assertIn("/packaging.css", shell)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        for path, content_type in [
            ("/packaging-model.js", "javascript"),
            ("/packaging-ui.js", "javascript"),
            ("/packaging.css", "text/css"),
        ]:
            code, content, response_headers = self.request(path)
            self.assertEqual(code, 200, path)
            self.assertIn(content_type, response_headers["Content-Type"])
            self.assertTrue(content)
            self.assertEqual(response_headers["X-Content-Type-Options"], "nosniff")

    def test_static_allowlist_does_not_expose_other_files(self):
        for path in [
            "/packaging-ui.js/private",
            "/packaging_store.py",
            "/static/packaging-ui.js",
            "/packaging.css/../db.py",
        ]:
            code, _, _ = self.request(path)
            self.assertNotEqual(code, 200, path)


if __name__ == "__main__":
    unittest.main()
