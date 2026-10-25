"""Serve the actual page-reporting assets under existing loopback boundaries."""
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen, Request
from mission_control.server import Server
from mission_control.store import Store


class PageReportingHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = Server(("127.0.0.1", 0), Store(Path(cls.tmp.name) / "test.sqlite"))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def test_page_explainers_assets_and_shared_view_integration(self):
        for route, mime in (("/", "text/html"), ("/page-reporting.js", "text/javascript"), ("/page-reporting.css", "text/css")):
            with urlopen(self.origin + route) as response:
                value = response.read().decode("utf-8")
                self.assertEqual(response.status, 200)
                self.assertIn(mime, response.headers["Content-Type"])
                self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
                self.assertNotIn("unsafe-inline", response.headers["Content-Security-Policy"])
                self.assertIn("page-reporting", value)
        with urlopen(self.origin + "/app.js") as response:
            value = response.read().decode("utf-8")
            self.assertIn("WMMPageReports.decorate(state,document)", value)
            self.assertIn("workspaceObservedAt=new Date().toISOString()", value)

    def test_report_privacy_preserves_static_allowlist_and_host_boundary(self):
        for route in ("/page-reporting.js/extra", "/page-reporting.css/extra", "/agent-checkpoints.json"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.origin + route)
            self.assertEqual(error.exception.code, 404)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.origin + "/page-reporting.js", headers={"Host":"external.example"}))
        self.assertEqual(error.exception.code, 403)
