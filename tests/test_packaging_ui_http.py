"""The real loopback server delivers the packaging UI without widening file access."""
import unittest
from tests.test_http import HTTPTests


class PackagingStaticTests(unittest.TestCase):
    setUp = HTTPTests.setUp
    tearDown = HTTPTests.tearDown
    request = HTTPTests.request

    def test_shell_loads_packaging_dependencies_in_order(self):
        code, body, headers = self.request('/')
        self.assertEqual(code, 200)
        shell = body.decode('utf-8')
        self.assertLess(shell.index('/packaging-model.js'), shell.index('/packaging-ui.js'))
        self.assertLess(shell.index('/packaging-ui.js'), shell.index('/app.js'))
        self.assertIn('/packaging.css', shell)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
        for path, content_type in [('/packaging-model.js', 'javascript'),
                                   ('/packaging-ui.js', 'javascript'),
                                   ('/packaging.css', 'text/css')]:
            code, content, response_headers = self.request(path)
            self.assertEqual(code, 200, path)
            self.assertIn(content_type, response_headers['Content-Type'])
            self.assertTrue(content)
            self.assertEqual(response_headers['X-Content-Type-Options'], 'nosniff')

    def test_static_allowlist_does_not_expose_other_files(self):
        for path in ['/packaging-ui.js/private', '/packaging_store.py',
                     '/static/packaging-ui.js', '/packaging.css/../db.py']:
            code, _, _ = self.request(path)
            self.assertNotEqual(code, 200, path)


if __name__ == '__main__':
    unittest.main()
