"""Adversarial provider primitives and explicit no-replay contract edges."""
import time,unittest
from mission_control.common import Invalid
from mission_control.social_auth import code_fields,refresh_fields
from mission_control.social_contract import provider_id,configuration_secret
from mission_control.social_profiles import facebook_expiry,facebook_page,next_cursor
from mission_control.social_tokens import token_object,parse_scopes,refresh_lifetime,credential_fields
from mission_control.social_transport import status_code
from tests.test_social_providers import config


class SocialBoundaryTests(unittest.TestCase):
    def test_code_fields_and_configuration_secret_keep_native_grants_secretless(self):
        fields,operation=code_fields(config('linkedin',True),'','synthetic-code','V'*64)
        self.assertEqual(operation,'code_native');self.assertNotIn('client_secret',fields)
        configuration_secret('linkedin',True,'')
        for args in (('linkedin',True,'synthetic-secret'),('facebook',False,'')):
            with self.assertRaises(Invalid):configuration_secret(*args)
        with self.assertRaises(Invalid):code_fields(config('tiktok'),'synthetic-secret','bad\ncode','V'*64)

    def test_refresh_fields_rejects_expired_or_missing_renewal_permission(self):
        facts={'refresh_expires_at':time.time()-1}
        with self.assertRaises(Invalid):refresh_fields(config('linkedin'),'synthetic-secret',{'refresh_token':'synthetic-refresh'},facts,time.time())
        with self.assertRaises(Invalid):refresh_fields(config('tiktok'),'synthetic-secret',{},facts,time.time())
        self.assertEqual(provider_id('tiktok'),'tiktok')
        for value in (None,{},'unregistered'):
            with self.assertRaises(Invalid):provider_id(value)

    def test_token_object_parse_scopes_credential_fields_and_refresh_lifetime(self):
        for value in (None,[],{'error':'denied'},{'data':{}},{'data':[{},{}]}):
            with self.assertRaises(Invalid):token_object(value)
        self.assertIsNone(parse_scopes('linkedin',{},{}))
        self.assertEqual(parse_scopes('instagram',{'permissions':['instagram_business_basic']},{}),['instagram_business_basic'])
        with self.assertRaises(Invalid):parse_scopes('tiktok',{}, {})
        self.assertEqual(credential_fields({'access_token':'synthetic','unneeded':'discard'}),{'access_token':'synthetic'})
        self.assertEqual(refresh_lifetime('linkedin',{'refresh_token_expires_in':3600},1000,{'refresh_expires_at':2000}),2000)
        self.assertIsNone(refresh_lifetime('linkedin',{},1000,{}))

    def test_facebook_expiry_and_facebook_page_do_not_invent_permanent_access(self):
        self.assertIsNone(facebook_expiry({'expires_at':0}))
        self.assertIsNone(facebook_expiry({}))
        with self.assertRaises(Invalid):facebook_expiry({'expires_at':True})
        with self.assertRaises(Invalid):facebook_expiry({'data_access_expires_at':int(time.time())-1})
        page=facebook_page(dict(id='123',name='Synthetic Page',tasks=['ANALYZE'],access_token='NEVER_RETURN'))
        self.assertNotIn('access_token',page)
        with self.assertRaises(Invalid):facebook_page(dict(id='123',name='Synthetic',tasks='MANAGE'))

    def test_next_cursor_and_status_code_do_not_forward_hosts_or_private_errors(self):
        self.assertIsNone(next_cursor({}))
        self.assertEqual(next_cursor({'paging':{'next':'https://attacker.invalid','cursors':{'after':'synthetic-cursor'}}}),'synthetic-cursor')
        with self.assertRaises(Invalid):next_cursor({'paging':{'next':'https://attacker.invalid'}})
        self.assertIsNone(status_code(200))
        for status in (301,400,403,429,500):
            with self.assertRaises(Invalid):status_code(status)


if __name__=='__main__':unittest.main()
