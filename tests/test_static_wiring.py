"""Validate the dashboard module graph and original behavior-body size limits.

Dependency declarations, including multiline imports and export lists, do not count toward the
body limits; the module graph separately checks their files and server routes.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "mission_control/static"
SCREEN_LIMIT = 800
SHELL_LIMIT = 1250


def scripts(html):
    return re.findall(r'<script[^>]+src="/([^"]+\.m?js)"', html)


def behavior_lines(source):
    declarations = re.compile(r"^import\s+(?:[^;]*?\s+from\s+)?['\"][^'\"]+['\"];[^\S\n]*\n?", re.M)
    body = declarations.sub("", source)
    body = re.sub(r"^export\s*\{[^}]*\};?\s*$", "", body, flags=re.M)
    return len(body.splitlines())


class StaticWiringTests(unittest.TestCase):
    def test_every_html_script_reference_exists(self):
        missing = []
        for page in sorted(STATIC.glob("*.html")):
            for name in scripts(page.read_text(encoding="utf-8")):
                if not any((base / name).is_file() for base in (STATIC, ROOT / "mission_control")):
                    missing.append((page.name, name))
        self.assertEqual(missing, [])

    def test_dashboard_entry_links_shell_and_screen_modules(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertEqual(scripts(html), ["dashboard.mjs"])
        self.assertRegex(html, r'<script type="module" src="/dashboard\.mjs"></script>')
        entry = (STATIC / "dashboard.mjs").read_text(encoding="utf-8")
        self.assertRegex(entry, r"import\s*\{\s*startApplication\s*\}\s*from\s*['\"]\./app\.mjs['\"];?")
        self.assertIn("startApplication()", entry)
        screens = sorted(path.name for path in STATIC.glob("app-*.mjs"))
        self.assertGreaterEqual(len(screens), 8)
        for name in screens:
            self.assertRegex(entry, rf"import\s*['\"]\./{re.escape(name)}['\"];?")
        features = (STATIC / "feature-apis.mjs").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"import\s*['\"]\./authority-expiry\.js['\"];?", features)), 1)
        visited = set()

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            source = STATIC / name
            self.assertTrue(source.is_file(), name)
            text = source.read_text(encoding="utf-8")
            for dependency in re.findall(r'^import[^;]*[\'"]\./([^\'"]+)[\'"];', text, re.M):
                visit(dependency)

        visit("dashboard.mjs")
        self.assertIn("feature-apis.mjs", visited)
        server = (ROOT / "mission_control/server.py").read_text(encoding="utf-8")
        for name in visited:
            self.assertIn(f'"/{name}"', server, name)

    def test_linked_assets_have_javascript_mime_and_exact_bytes(self):
        from urllib.request import urlopen

        from tests.test_campaign_access import CampaignGatewayTests

        host = CampaignGatewayTests()
        host.setUp()
        try:
            files = {p.name for p in STATIC.glob("*.mjs")}
            files.update(re.findall(r"import\s*['\"]\./([^'\"]+)['\"]", (STATIC / "feature-apis.mjs").read_text()))
            for name in sorted(files):
                with self.subTest(asset=name), urlopen(str(getattr(host, "origin")) + "/" + name, timeout=5) as response:
                    self.assertIn(response.headers.get_content_type(), ("text/javascript", "application/javascript"))
                    self.assertEqual(response.read(), (STATIC / name).read_bytes())
        finally:
            host.tearDown()

    def test_shell_and_screen_sizes_stay_bounded(self):
        self.assertLessEqual(behavior_lines((STATIC / "app.mjs").read_text(encoding="utf-8")), SHELL_LIMIT)
        for name in sorted(path.name for path in STATIC.glob("app-*.mjs")):
            self.assertLessEqual(behavior_lines((STATIC / name).read_text(encoding="utf-8")), SCREEN_LIMIT, name)

    def test_index_scripts_are_served_by_the_main_server(self):
        server = (ROOT / "mission_control/server.py").read_text(encoding="utf-8")
        for name in scripts((STATIC / "index.html").read_text(encoding="utf-8")):
            self.assertIn(f'"/{name}"', server, name)


if __name__ == "__main__":
    unittest.main()
