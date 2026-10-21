"""Real loopback request boundaries; site reads use the explicit synthetic inspector fixture."""
import http.client
import http.cookiejar
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, HTTPCookieProcessor, build_opener
from unittest.mock import patch
from mission_control.server import Server
from mission_control.common import digest
from mission_control.aeo_transport import ReadError
from tests.test_setup_discovery import SetupFixture
from tests.test_aeo_inspection import Reader, ROOT


class SetupHTTPTests(SetupFixture):
    def setUp(self):
        super().setUp()
        self.reader = Reader()
        self.reader_patch = patch('mission_control.setup_discovery.PublicReader', return_value=self.reader)
        self.reader_patch.start()
        self.addCleanup(self.reader_patch.stop)
        self.server = Server(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.cookies = http.cookiejar.CookieJar()
        self.client = build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf = self.request('/api/bootstrap')[1]['csrf']
        self.path = '/api/apps/sample-one/setup-discovery'

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path, body=None, headers=None, raw=None):
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        fields = {'Origin':self.base, 'Content-Type':'application/json', 'X-CSRF-Token':getattr(self, 'csrf', '')}
        fields.update(headers or {})
        request = Request(self.base + path, data=data, headers=fields)
        try:
            response = self.client.open(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def discover(self):
        code, row = self.request(self.path + '/discover', self.body())
        self.assertEqual(code, 200, row)
        return row

    def rejected_headers(self, headers):
        """Send headers only: urllib adds chunk framing after an early rejection."""
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        fields = {'Origin': self.base, 'Content-Type': 'application/json', 'Content-Length': '0',
                  'Cookie': '; '.join(cookie.name + '=' + cookie.value for cookie in self.cookies),
                  'X-CSRF-Token': self.csrf}
        fields.update(headers)
        try:
            client.putrequest('POST', self.path + '/discover')
            for name, value in fields.items():
                client.putheader(name, value)
            client.endheaders()
            response = client.getresponse()
            response.read()
            return response.status
        finally:
            client.close()

    def approval(self, row):
        app = self.store.app('sample-one')
        return dict(app_id='sample-one', id=row['id'], proposal_hash=row['hash'], app_version=app['version'],
                    app_hash=digest(app['data']), changes={'name':'Real app'}, confirm_apply=True)

    def test_discover_review_apply_reload_and_delete_are_distinct_actions(self):
        before = self.store.app('sample-one')
        row = self.discover()
        self.assertEqual(row['currentness'], 'PENDING')
        self.assertEqual(self.store.app('sample-one'), before)
        code, detail = self.request(self.path + '/' + row['id'])
        self.assertEqual(code, 200)
        self.assertEqual(detail['data']['source_url'], ROOT + '/page')
        code, workspace = self.request('/api/apps/sample-one')
        summary = workspace['setup_discovery']['proposals'][0]
        self.assertEqual(summary['id'], row['id'])
        self.assertNotIn('data', summary)
        self.assertLess(len(json.dumps(workspace['setup_discovery']).encode()), 4000)
        body = self.approval(row)
        self.assertEqual(self.request(self.path + '/apply', body)[1]['status'], 'APPLIED')
        saved = self.store.app('sample-one')
        self.assertEqual(self.request(self.path + '/apply', body)[0], 400)
        self.assertEqual(self.request(self.path + '/delete', dict(id=row['id'], hash=row['hash'], confirm_delete=True))[1]['status'], 'DELETED')
        self.assertEqual(self.store.app('sample-one'), saved)

    def test_host_origin_csrf_fail_before_site_read(self):
        path = self.path + '/discover'
        for headers in ({'Host':'foreign.example'}, {'Origin':'https://foreign.example'}, {'X-CSRF-Token':'wrong'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(path, self.body(), headers=headers, raw=b'')[0], 403)
        self.assertFalse(self.reader.calls)

    def test_exact_json_framing_types_and_size_do_not_reach_reader(self):
        path = self.path + '/discover'
        for raw in (b'{"confirm_read":true,"confirm_read":false}', b'{"value":NaN}', b'[]'):
            self.assertEqual(self.request(path, raw=raw)[0], 400)
        for headers in ({'Content-Type':'text/plain'}, {'Transfer-Encoding':'chunked'}, {'Content-Length':'8193'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.rejected_headers(headers), 400)
        self.assertEqual(self.request(path + '?override=true', self.body())[0], 400)
        self.assertEqual(self.request(path, {**self.body(), 'url':'https://foreign.example/'})[0], 400)
        self.assertEqual(self.request(self.path + '/arbitrary-command', self.body())[0], 400)
        self.assertFalse(self.reader.calls)

    def test_duplicate_content_lengths_are_rejected(self):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=20)
        try:
            client.putrequest('POST', self.path + '/discover')
            client.putheader('Origin', self.base)
            client.putheader('Content-Type', 'application/json')
            client.putheader('Cookie', '; '.join(cookie.name + '=' + cookie.value for cookie in self.cookies))
            client.putheader('X-CSRF-Token', self.csrf)
            client.putheader('Content-Length', '0')
            client.putheader('Content-Length', '0')
            client.endheaders()
            response = client.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            client.close()
        self.assertFalse(self.reader.calls)

    def test_foreign_scope_and_query_do_not_reuse_proposals(self):
        row = self.discover()
        foreign = '/api/apps/sample-two/setup-discovery'
        self.assertEqual(self.request(foreign + '/' + row['id'])[0], 400)
        self.assertEqual(self.request(foreign + '/apply', self.approval(row))[0], 400)
        self.assertEqual(self.request(foreign + '/discover', self.body())[0], 400)
        self.assertEqual(self.request(self.path + '/' + row['id'] + '?refresh=true')[0], 400)
        self.assertEqual(self.service.get('sample-one', row['id'])['state'], 'PENDING')

    def test_network_denial_has_recovery_instead_of_false_empty_success(self):
        self.reader.resources[ROOT + '/page'] = ReadError('NETWORK_FAILED')
        row = self.discover()
        self.assertEqual(row['state'], 'NEEDS_RESOLUTION')
        self.assertIsNone(row['data']['projection'])
        self.assertTrue(row['data']['recovery'])
        self.assertEqual(self.request(self.path + '/apply', self.approval(row))[0], 400)
