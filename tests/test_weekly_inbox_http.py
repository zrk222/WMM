import json
from tests.test_aeo_http import HTTPTests


class InboxHTTPTests(HTTPTests):
    def test_review_route_and_boundary(self):
        code,headers,raw=self.request('/api/weekly-review?offset=0')
        self.assertEqual(code,200)
        result=json.loads(raw)
        self.assertEqual(result['coverage']['evaluated'],1)
        self.assertFalse(result['spend_allowed'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.request('/api/weekly-review',headers={'Host':'evil.example'})[0],403)
        for query in ('?offset=-1','?offset=0&offset=1','?offset=0&extra=1'):
            self.assertEqual(self.request('/api/weekly-review'+query)[0],400)
