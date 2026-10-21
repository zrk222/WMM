"""Real loopback HTTP boundaries with synthetic Google responses, never live credentials."""
import http.cookiejar
import json
import threading
from urllib.error import HTTPError
from urllib.parse import parse_qs,urlsplit
from urllib.request import Request,HTTPCookieProcessor,build_opener
from unittest.mock import patch
from mission_control import play_auth
from mission_control.server import Server
from mission_control.worker import run_once
from tests.test_play_worker import PlayFixture
from tests.test_play_connections import CONFIG,GRANT


class PlayHTTPTests(PlayFixture):
    def setUp(self):
        super().setUp()
        patch('mission_control.play_connections.Vault',return_value=self.vault).start()
        self.exchange=patch.object(play_auth,'exchange',return_value=GRANT).start()
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf=self.request('/api/bootstrap')[1]['csrf']

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,body=None,headers=None,raw=None):
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        fields={'Origin':self.base,'Content-Type':'application/json','X-CSRF-Token':getattr(self,'csrf','')}
        fields.update(headers or {})
        request=Request(self.base+path,data=data,headers=fields)
        try:response=self.client.open(request,timeout=10)
        except HTTPError as error:response=error
        with response:
            raw=response.read()
            result=json.loads(raw) if response.headers.get('Content-Type','').startswith('application/json') else raw
            return response.status,result,response.headers

    def start(self,app='sample-one'):
        current=self.store.app(app)
        body=dict(package_name=self.data['package_name'],track='production',manifest_version=current['version'],
                  connection_id=self.record['id'] if app=='sample-one' else None,
                  connection_version=self.record['version'] if app=='sample-one' else 0,
                  client_json=json.dumps({'installed':CONFIG}),confirm_read=True)
        code,result,_=self.request(f'/api/apps/{app}/play/start',body)
        self.assertEqual(code,200,result)
        return result,parse_qs(urlsplit(result['authorization_url']).query)['state'][0]

    def test_discovery_has_no_saved_side_effect_and_rejects_ambiguous_json(self):
        path='/api/apps/sample-one/play/discover'
        old=self.store.app('sample-one')
        code,value,_=self.request(path,dict(kind='app.json',text='{"expo":{"android":{"package":"com.example.app"}}}'))
        self.assertEqual(code,200,value);self.assertEqual(value['package_candidates'],['com.example.app'])
        self.assertEqual(self.store.app('sample-one'),old)
        self.assertEqual(self.request(path,raw=b'{"kind":"app.json","kind":"other","text":"{}"}')[0],400)
        self.assertEqual(self.request(path,raw=b'{"kind":"app.json","text":NaN}')[0],400)
        self.assertEqual(self.request(path,dict(kind='app.json',text='{}',execute=True))[0],400)
        self.assertEqual(self.request(path,dict(kind='app.json',text='x'*131073))[0],400)

    def test_csrf_origin_host_and_framing_stop_before_consent(self):
        path='/api/apps/sample-one/play/discover';body=dict(kind='app.json',text='{}')
        for headers in ({'X-CSRF-Token':'wrong'},{'Origin':'https://foreign.example'},{'Host':'foreign.example'}):
            self.assertEqual(self.request(path,body,headers)[0],403)
        for headers in ({'Content-Type':'text/plain'},{'Transfer-Encoding':'chunked'}):
            self.assertEqual(self.request(path,body,headers,raw=b'')[0],400)
        self.assertEqual(self.request(path+'?override=true',body)[0],400)
        self.exchange.assert_not_called()

    def test_setup_actual_port_and_callback_single_use_and_private_assets(self):
        result,state=self.start()
        query=parse_qs(urlsplit(result['authorization_url']).query)
        self.assertEqual(query['redirect_uri'],[self.base])
        path='/?state='+state+'&code=synthetic-code'
        code,html,headers=self.request(path)
        self.assertEqual(code,200);self.assertIn(b'play-callback.js',html)
        self.assertNotIn(b'/app.js',html);self.assertNotIn(b'synthetic-code',html)
        self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        self.exchange.assert_not_called()
        body=dict(state=state,code='synthetic-code')
        self.assertEqual(self.request('/api/play/callback',body,{'X-CSRF-Token':'wrong'})[0],403)
        code,saved,_=self.request('/api/play/callback',body)
        self.assertEqual(code,200,saved);self.assertEqual(saved['status'],'CONNECTED')
        self.assertEqual(saved['app_id'],'sample-one')
        flows=self.request('/api/apps/sample-one')[1]['play']['flows']
        record=next(r for r in self.store.records('sample-one') if r['id']==saved['connection_id'])
        self.assertEqual(flows[0]['result']['connection_version'],record['version'])
        self.assertEqual(self.request('/api/play/callback',body)[0],400)
        self.exchange.assert_called_once()
        for asset in ('/google-play.js','/play-callback.js'):
            self.assertEqual(self.request(asset)[0],200)
        public=json.dumps(self.request('/api/apps/sample-one')[1])
        for secret in (CONFIG['client_secret'],GRANT['refresh_token'],state,'synthetic-code'):
            self.assertNotIn(secret,public)

    def test_callback_exact_shape_cancellation_and_cross_app_denial(self):
        result,state=self.start();path='/api/play/callback'
        self.assertEqual(self.request(path,dict(state=state,code='x',return_url='https://foreign.example'))[0],400)
        cancel=dict(flow_id=result['flow_id'])
        self.assertEqual(self.request('/api/apps/sample-two/play/cancel',cancel)[0],400)
        self.assertEqual(self.request('/api/apps/sample-one/play/cancel',cancel)[0],200)
        self.assertEqual(self.request(path,dict(state=state,code='x'))[0],400)
        self.exchange.assert_not_called()

    def test_typed_read_real_queue_and_foreign_target_denial(self):
        body=dict(connection_id=self.record['id'],connection_version=self.record['version'],
                  manifest_version=self.store.app('sample-one')['version'],operation='play_releases',request_key='http-read')
        path='/api/apps/sample-one/play/read'
        code,job,_=self.request(path,body);self.assertEqual(code,200,job)
        self.assertEqual(job['status'],'QUEUED');self.assertTrue(run_once(self.store))
        self.assertEqual(self.result(job['id'])['status'],'SUCCEEDED')
        self.assertEqual(self.request('/api/apps/sample-two/play/read',body)[0],400)
        self.assertEqual(self.request(path,{**body,'operation':'publish'})[0],400)
        self.assertEqual(self.request(path,{**body,'manifest_version':0})[0],400)
