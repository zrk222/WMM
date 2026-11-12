"""Static assets revalidate by build-bound ETag while API responses stay no-store."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mission_control.server import Server
from mission_control.store import Store


class StaticAssetETagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = Server(("127.0.0.1", 0), Store(Path(self.tmp.name) / "state.sqlite"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def get(self, path, headers=None):
        request = Request(self.base + path, headers=headers or {})
        try:
            response = urlopen(request)
        except HTTPError as error:
            return error.code, error.headers, error.read()
        return response.status, response.headers, response.read()

    def test_static_asset_etag_and_conditional_304(self):
        code, headers, raw = self.get("/style.css")
        self.assertEqual(code, 200)
        self.assertTrue(raw)
        tag = headers["ETag"]
        self.assertTrue(tag)
        self.assertEqual(headers["Cache-Control"], "no-cache")
        code, headers, raw = self.get("/style.css", {"If-None-Match": tag})
        self.assertEqual(code, 304)
        self.assertEqual(raw, b"")
        self.assertEqual(headers["ETag"], tag)
        code, headers, _ = self.get("/style.css", {"If-None-Match": f"W/{tag}"})
        self.assertEqual(code, 304)

    def test_distinct_assets_and_build_bound_tags(self):
        _, first, _ = self.get("/style.css")
        _, second, _ = self.get("/app.js")
        self.assertNotEqual(first["ETag"], second["ETag"])
        build = self.server.service.build_id or ""
        self.server.service.build_id = build + "-other"
        _, changed, _ = self.get("/style.css")
        self.assertNotEqual(first["ETag"], changed["ETag"])

    def test_api_responses_keep_no_store_and_no_etag(self):
        code, headers, raw = self.get("/api/bootstrap")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIsNone(headers["ETag"])
        self.assertIn("apps", json.loads(raw))


if __name__ == "__main__":
    unittest.main()
