"""Single-use callbacks, identity failure, races, expiry and no credential leakage."""
import hashlib,tempfile,time,unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
from mission_control.common import Invalid,canonical,now
from mission_control.store import Store
from mission_control.db import connection
from mission_control.social_setup import Setup
from mission_control.social_flows import Flows,public
from mission_control.social_callbacks import callback
from mission_control.social_profiles import Identity
from mission_control.social_tokens import parse
from mission_control.social_registry import PROVIDERS
from mission_control.social_secrets import Secrets
from tests.test_measurement_connectors import FakeVault
from tests.test_social_setup import body
from tests.test_social_providers import token


class SocialFlowTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.store=Store(Path(folder.name)/'synthetic.sqlite3');self.setup=Setup(self.store);self.flows=Flows(self.store)
        FakeVault.values={};FakeVault.fail_delete=0
        vault=patch('mission_control.social_secrets.Vault',FakeVault);vault.start();self.addCleanup(vault.stop)
        self.setup.save('sample-one',{**body('tiktok'),'redirect_uri':''})

    def begin(self):
        started=self.flows.start('sample-one','tiktok',1)
        state=parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
        request=dict(provider='tiktok',state=state,code='synthetic-code',error='')
        return started,request

    def success(self,request):
        grant=parse('tiktok',token(),time.time())
        identity=Identity('synthetic-user','Synthetic person',[dict(id='synthetic-user',name='Synthetic person',kind='PROFILE',tasks=[])],['user.info.basic'])
        with patch('mission_control.social_callbacks.exchange_code',return_value=grant),patch('mission_control.social_callbacks.verify',return_value=identity):
            return callback(self.store,request)

    def test_raw_state_code_and_verifier_never_enter_sqlite_or_public_progress(self):
        started,request=self.begin();row=self.flows.get('sample-one',started['flow_id'])
        with connection(self.store.path) as db:raw=str([tuple(r) for r in db.execute('SELECT * FROM social_flows')])
        self.assertNotIn(request['state'],raw);self.assertNotIn('synthetic-code',raw)
        self.assertEqual(row['state_hash'],hashlib.sha256(request['state'].encode()).hexdigest())
        result=self.success(request)
        self.assertEqual(result['status'],'AWAITING_DESTINATION')
        self.assertNotIn('synthetic-access',canonical(result));self.assertNotIn('secret_ref',canonical(result))
        self.assertNotIn('state_hash',canonical(result))
        with self.assertRaises(Invalid):self.flows.get('sample-two',started['flow_id'])

    def test_callback_is_single_use_and_survives_reopen(self):
        started,request=self.begin();self.success(request)
        self.assertEqual(Flows(Store(self.store.path)).get('sample-one',started['flow_id'])['status'],'AWAITING_DESTINATION')
        with patch('mission_control.social_callbacks.exchange_code') as network:
            with self.assertRaisesRegex(Invalid,'already used'):callback(self.store,request)
            network.assert_not_called()

    def test_facebook_long_exchange_missing_ttl_requires_inspected_future_expiry(self):
        self.setup.save('sample-one',body('facebook'))
        permissions=PROVIDERS['facebook']['scopes'];expiry=int(time.time())+3600
        for inspected,ttl,expected in [(expiry,None,'AWAITING_DESTINATION'),(None,None,'UNCONFIRMED'),
                                       (0,None,'UNCONFIRMED'),(True,None,'UNCONFIRMED'),
                                       (int(time.time())-1,None,'UNCONFIRMED'),
                                       (int(time.time())+6*366*86400,None,'UNCONFIRMED'),
                                       (expiry,7200,'AWAITING_DESTINATION'),(expiry,600,'AWAITING_DESTINATION')]:
            with self.subTest(inspected=inspected,ttl=ttl):
                started=self.flows.start('sample-one','facebook',1)
                state=parse_qs(urlsplit(started['authorization_url']).query)['state'][0]
                request=dict(provider='facebook',state=state,code='synthetic-code',error='')
                meta=[dict(access_token='synthetic-app-access'),
                      dict(data=dict(is_valid=True,app_id='123456',user_id='123',scopes=permissions,expires_at=inspected)),
                      dict(id='123',name='Synthetic person'),
                      dict(data=[dict(permission=s,status='granted') for s in permissions]),dict(data=[])]
                long=dict(access_token='synthetic-long',token_type='bearer')
                if ttl is not None:long['expires_in']=ttl
                before=time.time()
                stage=Secrets.stage
                with patch('mission_control.social_auth.request',side_effect=[dict(access_token='synthetic-short',token_type='bearer'),long]),\
                     patch('mission_control.social_profiles.request',side_effect=meta),\
                     patch.object(Secrets,'stage',autospec=True,side_effect=stage) as staging:
                    result=callback(self.store,request)
                self.assertEqual(staging.call_count,1 if expected=='AWAITING_DESTINATION' else 0)
                self.assertEqual(result['status'],expected)
                if expected=='AWAITING_DESTINATION':
                    expires=result['data']['facts']['expires_at']
                    if ttl==600:self.assertTrue(before+600<=expires<=time.time()+600)
                    else:self.assertEqual(expires,expiry)
                    self.flows.stop('sample-one',started['flow_id'])
                else:
                    self.assertNotIn('synthetic-long',str(FakeVault.values))
                with patch('mission_control.social_callbacks.exchange_code') as network:
                    with self.assertRaises(Invalid):callback(self.store,request)
                    network.assert_not_called()

    def test_wrong_provider_expired_or_changed_setup_cannot_exchange(self):
        started,request=self.begin()
        with patch('mission_control.social_callbacks.exchange_code') as network:
            with self.assertRaises(Invalid):callback(self.store,{**request,'provider':'linkedin'})
            self.setup.save('sample-one',{**body('tiktok'),'redirect_uri':'','version':1})
            with self.assertRaises(Invalid):callback(self.store,request)
            network.assert_not_called()
        self.assertEqual(self.flows.get('sample-one',started['flow_id'])['status'],'CONFIG_CHANGED')

    def test_denial_consumes_state_and_discards_verifier_without_token_exchange(self):
        started,request=self.begin()
        with patch('mission_control.social_callbacks.exchange_code') as network:
            result=callback(self.store,{**request,'code':'','error':'access_denied'});network.assert_not_called()
        self.assertEqual(result['status'],'DECLINED');self.assertIsNone(self.flows.get('sample-one',started['flow_id'])['secret_ref'])
        self.assertEqual(len(FakeVault.values),1)

    def test_ambiguous_exchange_stays_terminal_and_does_not_replay(self):
        started,request=self.begin()
        with patch('mission_control.social_callbacks.exchange_code',side_effect=OSError('SECRET_MUST_NOT_SURFACE')) as network:
            result=callback(self.store,request)
            self.assertEqual(result['status'],'UNCONFIRMED');self.assertNotIn('SECRET',canonical(result))
            with self.assertRaises(Invalid):callback(self.store,request)
            self.assertEqual(network.call_count,1)

    def test_cancel_during_exchange_prevents_adoption_and_preserves_config(self):
        started,request=self.begin()
        def interrupted(*args):
            self.flows.stop('sample-one',started['flow_id']);return parse('tiktok',token(),time.time())
        with patch('mission_control.social_callbacks.exchange_code',side_effect=interrupted):result=callback(self.store,request)
        self.assertEqual(result['status'],'CANCELLED')
        self.assertEqual(self.setup.get('sample-one','tiktok')['version'],1)

    def test_expiry_recovers_interrupted_exchange_without_retry(self):
        started,request=self.begin();self.flows.claim('tiktok',request['state'])
        with connection(self.store.path) as db:db.execute('UPDATE social_flows SET expires=? WHERE id=?',(time.time()-1,started['flow_id']))
        self.assertEqual(self.flows.expire('sample-one'),1)
        self.assertEqual(self.flows.get('sample-one',started['flow_id'])['status'],'UNCONFIRMED')


if __name__=='__main__':unittest.main()
