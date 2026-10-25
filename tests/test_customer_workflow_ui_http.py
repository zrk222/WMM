"""Customer authoring script integration through real loopback/static boundaries."""
import unittest
from tests import test_http


class CustomerWorkflowUIHTTPTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

    def test_customer_workflow_ui_is_served_and_embedded_with_existing_results(self):
        code, content, headers = self.request('/customer-workflow.js')
        self.assertEqual(code, 200)
        self.assertIn('text/javascript', headers['Content-Type'])
        self.assertIn('WMMCustomerWorkflow', content.decode('utf-8'))
        self.assertIn('/customer-workflow.js', self.request('/')[1].decode('utf-8'))
        source = self.request('/app.js')[1].decode('utf-8')
        for expected in ('WMMCustomerWorkflow.panel(state)', 'WMMCustomerWorkflow.submit(form,growthReviewServices())', 'WMMCustomerWorkflow.action(node,growthReviewServices())', 'legacyResultsView()'):
            self.assertIn(expected, source)
        self.assertEqual(self.request('/api/apps/sample-one')[1]['subscription_growth']['customer_workflows']['app_id'], 'sample-one')

    def test_customer_script_keeps_exact_static_and_host_boundaries(self):
        self.assertEqual(self.request('/customer-workflow.js/extra')[0], 404)
        self.assertEqual(self.request('/customer-workflow.js', headers={'Host':'external.example'})[0], 403)
        self.assertEqual(self.request('/customer-workflow-ui.json')[0], 404)
