"""Real script serving and existing workspace/static boundaries for growth review UI."""
import unittest
from tests import test_http


class GrowthReviewUIHTTPTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

    def test_growth_review_module_is_served_and_integrated_without_dropping_results(self):
        code, script, headers = self.request('/growth-review.js')
        self.assertEqual(code, 200)
        script = script.decode('utf-8')
        self.assertIn('WMMGrowthReview', script)
        self.assertIn('text/javascript', headers['Content-Type'])
        self.assertIn('/growth-review.js', self.request('/')[1].decode('utf-8'))
        source = self.request('/app.js')[1].decode('utf-8')
        self.assertIn('WMMGrowthReview.panel(state)', source)
        self.assertIn('measurementIntegrityPanel()', source)
        self.assertIn('WMMGrowthReview.submit(form,growthReviewServices())', source)
        self.assertIn('legacyResultsView()', source)
        workspace = self.request('/api/apps/sample-one')[1]
        self.assertEqual(workspace['subscription_growth']['app_id'], 'sample-one')

    def test_script_keeps_exact_static_allowlist_and_host_boundary(self):
        self.assertEqual(self.request('/growth-review.js/extra')[0], 404)
        self.assertEqual(self.request('/growth-review.js', headers={'Host':'external.example'})[0], 403)
        self.assertEqual(self.request('/growth-review-history.json')[0], 404)


if __name__ == '__main__':
    unittest.main()
