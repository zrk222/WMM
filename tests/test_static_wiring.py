"""Static HTML script references resolve and screen modules load before the shell."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "mission_control/static"
SCREEN_LIMIT = 800
SHELL_LIMIT = 1250


def scripts(html):
    return re.findall(r'<script[^>]+src="/([^"]+\.js)"', html)


class StaticWiringTests(unittest.TestCase):
    def test_every_html_script_reference_exists(self):
        missing = []
        for page in sorted(STATIC.glob("*.html")):
            for name in scripts(page.read_text(encoding="utf-8")):
                if not any((base / name).is_file() for base in (STATIC, ROOT / "mission_control")):
                    missing.append((page.name, name))
        self.assertEqual(missing, [])

    def test_screen_modules_load_before_the_shell(self):
        order = scripts((STATIC / "index.html").read_text(encoding="utf-8"))
        self.assertIn("app.js", order)
        shell = order.index("app.js")
        screens = sorted(path.name for path in STATIC.glob("app-*.js"))
        self.assertGreaterEqual(len(screens), 8)
        for name in screens:
            self.assertIn(name, order)
            self.assertLess(order.index(name), shell, name)

    def test_shell_and_screen_sizes_stay_bounded(self):
        self.assertLessEqual(len((STATIC / "app.js").read_text(encoding="utf-8").splitlines()), SHELL_LIMIT)
        for name in sorted(path.name for path in STATIC.glob("app-*.js")):
            self.assertLessEqual(len((STATIC / name).read_text(encoding="utf-8").splitlines()), SCREEN_LIMIT, name)

    def test_index_scripts_are_served_by_the_main_server(self):
        server = (ROOT / "mission_control/server.py").read_text(encoding="utf-8")
        for name in scripts((STATIC / "index.html").read_text(encoding="utf-8")):
            self.assertIn(f'"/{name}"', server, name)


if __name__ == "__main__":
    unittest.main()
