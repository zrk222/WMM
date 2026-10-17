"""Real private HTTP boundary, exact JSON, callback consumption and account scope."""
import json,time,unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
from tests import test_http as fixtures
from tests.test_measurement_connectors import FakeVault
from tests.test_social_setup import body
from tests.test_social_providers import token
from mission_control.social_tokens import parse
from mission_control.social_profiles import Identity


class SocialHTTPTests(unittest.TestCase):
    setUp=fixtures.HTTPTests.setUp
    tearDown=fixtures.HTTPTests.tearDown

    def request(self,path,body=None,headers=None,raw=None):
        return fixtures.HTTPTests.request(self,path,body,{'Content-Type':'application/json',**(headers or {})},raw)

    def test_strict_setup_scope_unknown_authority_and_static_callbacks(self):
        FakeVault.values={};base='/api/apps/sample-one/social-access'
        with patch('mission_control.social_secrets.Vault',FakeVault):
            self.assertEqual(self.request(base+'/save',body(),{'X-CSRF-Token':'bad'})[0],403)
            for path,data in ((base+'/save?bad=1',body()),(base+'/save',{**body(),'command':'bad'}),(base+'/publish',{})):
                self.assertEqual(self.request(path,data)[0],400)
            self.assertEqual(self.request(base+'/save',body(),{'Content-Type':'text/plain'})[0],400)
            duplicate=json.dumps(body())[:-1]+',"provider":"linkedin"}'
            self.assertEqual(self.request(base+'/save',raw=duplicate.encode())[0],400)
            self.assertEqual(self.request(base+'/save',body())[0],200)
            workspace=self.request('/api/apps/sample-one')[1]
            self.assertNotIn('synthetic-client-secret',json.dumps(workspace));self.assertNotIn('secret_ref',json.dumps(workspace['social_access']))
            self.assertEqual(self.request('/api/apps/sample-two')[1]['social_access']['setup']['configurations'],[])
        for route in ('/social-access.js','/social-callback.js','/social/callback/tiktok'):
            self.assertEqual(self.request(route)[0],200)
        self.assertEqual(self.request('/social/callback/unknown')[0],404)

    def test_official_callback_requires_csrf_and_is_consumed_once(self):
        FakeVault.values={};base='/api/apps/sample-one/social-access'
        with patch('mission_control.social_secrets.Vault',FakeVault):
            self.assertEqual(self.request(base+'/save',{**body('tiktok'),'redirect_uri':''})[0],200)
            started=self.request(base+'/start',dict(provider='tiktok',version=1))[1]
            query=parse_qs(urlsplit(started['authorization_url']).query)
            self.assertEqual(query['redirect_uri'][0],f'http://127.0.0.1:{self.server.server_port}/social/callback/tiktok')
            request=dict(provider='tiktok',state=query['state'][0],code='synthetic-code',error='')
            self.assertEqual(self.request('/api/social/callback',request,{'X-CSRF-Token':'wrong'})[0],403)
            found=Identity('synthetic-user','Synthetic account',[dict(id='synthetic-user',name='Synthetic account',kind='PROFILE',tasks=[])],['user.info.basic'])
            with patch('mission_control.social_callbacks.exchange_code',return_value=parse('tiktok',token(),time.time())),patch('mission_control.social_callbacks.verify',return_value=found):
                code,result,_=self.request('/api/social/callback',request)
            self.assertEqual(code,200);self.assertEqual(result['status'],'AWAITING_DESTINATION')
            self.assertEqual(self.request('/api/social/callback',request)[0],400)
            self.assertNotIn('synthetic-access',json.dumps(result));self.assertNotIn('state_hash',json.dumps(result))
            flow=started['flow_id']
            self.assertEqual(self.request('/api/apps/sample-two/social-access/flows/'+flow)[0],400)
            self.assertEqual(self.request(base+'/flows/'+flow+'?bad=1')[0],400)
            saved=self.request(base+'/confirm',dict(flow_id=flow,destination_id='synthetic-user',connection_id='',version=0))[1]
            self.assertEqual(saved['status'],'CONNECTED_READ_TESTED')
            self.assertEqual(self.request('/api/apps/sample-two/social-access/'+saved['id']+'/disconnect',{'version':1})[0],400)
            self.assertEqual(self.request(base+'/'+saved['id']+'/disconnect',{'version':1})[0],200)


if __name__=='__main__':unittest.main()
