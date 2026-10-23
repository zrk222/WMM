"""Subscription authoring integration uses existing exact loopback routes."""
import unittest
from tests import test_http

class SubscriptionAuthoringHTTPTests(unittest.TestCase):
    setUp=test_http.HTTPTests.setUp
    tearDown=test_http.HTTPTests.tearDown
    request=test_http.HTTPTests.request

    def test_served_module_and_results_dispatch(self):
        code,body,headers=self.request('/subscription-authoring.js')
        self.assertEqual(code,200)
        self.assertIn('text/javascript',headers['Content-Type'])
        self.assertIn('WMMSubscriptionAuthoring',body.decode())
        self.assertIn('/subscription-authoring.js',self.request('/')[1].decode())
        source=self.request('/app.js')[1].decode()
        for value in ('WMMSubscriptionAuthoring.panel(state)','WMMSubscriptionAuthoring.submit(form,growthReviewServices())','WMMSubscriptionAuthoring.action(node,growthReviewServices())','legacyResultsView()'):
            self.assertIn(value,source)

    def test_static_exact_route_and_host(self):
        self.assertEqual(self.request('/subscription-authoring.js/extra')[0],404)
        self.assertEqual(self.request('/subscription-authoring.js',headers={'Host':'external.example'})[0],403)
