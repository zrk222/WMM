"""Subscription authoring integration uses existing exact loopback routes."""

import re
import unittest

from tests import test_http


class SubscriptionAuthoringHTTPTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

    def test_served_module_and_results_dispatch(self):
        code, body, headers = self.request("/subscription-authoring.js")
        self.assertEqual(code, 200)
        self.assertIn("text/javascript", headers["Content-Type"])
        self.assertIn("WMMSubscriptionAuthoring", body.decode())
        html = self.request("/")[1].decode("utf-8")
        self.assertEqual(re.findall(r'<script\b[^>]*src="([^"]+)"', html), ["/dashboard.mjs"])
        self.assertIn('type="module" src="/dashboard.mjs"', html)
        code, adapter, headers = self.request("/feature-apis.mjs")
        self.assertEqual(code, 200)
        self.assertIn("text/javascript", headers["Content-Type"])
        imports = re.findall(r"^import ['\"]([^'\"]+)['\"];", adapter.decode(), re.M)
        self.assertEqual(imports.count("./subscription-authoring.js"), 1)
        source = re.sub(
            r"\s+",
            "",
            (
                self.request("/app.mjs")[1] + self.request("/app-results.mjs")[1] + self.request("/app-events.mjs")[1]
            ).decode(),
        )
        for value in (
            "WMMSubscriptionAuthoring.panel(state)",
            "WMMSubscriptionAuthoring.submit(form,growthReviewServices())",
            "WMMSubscriptionAuthoring.action(node,growthReviewServices())",
            "legacyResultsView()",
        ):
            self.assertIn(value, source)

    def test_static_exact_route_and_host(self):
        self.assertEqual(self.request("/subscription-authoring.js/extra")[0], 404)
        self.assertEqual(self.request("/subscription-authoring.js", headers={"Host": "external.example"})[0], 403)
