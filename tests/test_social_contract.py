"""Protocol identity, documented PKCE formats, redirect and permission boundaries."""
import base64,hashlib,unittest
from mission_control.common import Invalid
from mission_control.social_registry import catalog,PROVIDERS
from mission_control.social_contract import configuration,challenge,reported_scopes,seconds,account_id,display,reference


def setup(provider='tiktok',native=False):
    return dict(provider=provider,client_id='123456789' if provider in ('facebook','instagram') else 'synthetic-client.apps.googleusercontent.com' if provider=='youtube' else 'synthetic-client',
                client_secret='' if native else 'synthetic-client-secret',native_enabled=native,
                redirect_uri='' if provider=='tiktok' or native else 'https://relay.example/cb/'+provider,version=0)


class SocialContractTests(unittest.TestCase):
    def test_all_five_protocols_have_separate_read_first_scopes(self):
        self.assertEqual(set(catalog()),{'facebook','instagram','tiktok','linkedin','youtube'})
        for name in PROVIDERS:
            value=configuration(setup(name));self.assertEqual(value['scopes'],PROVIDERS[name]['scopes'])
            self.assertNotIn('client_secret',value)
            self.assertTrue(catalog()[name]['publishing_implemented']);self.assertFalse(catalog()[name]['automatic_ad_spend'])
            self.assertEqual(catalog()[name]['paid_campaign_execution_implemented'],name=='facebook')
        self.assertNotIn('instagram_basic',PROVIDERS['instagram']['scopes'])

    def test_facebook_campaign_permissions_require_explicit_new_setup_selection(self):
        base=configuration(setup('facebook'))
        self.assertNotIn('pages_manage_posts',base['scopes'])
        publish=configuration({**setup('facebook'),'campaign_access':'publish'})
        self.assertIn('pages_manage_posts',publish['scopes'])
        self.assertNotIn('ads_management',publish['scopes'])
        paid=configuration({**setup('facebook'),'campaign_access':'ads'})
        self.assertTrue({'pages_manage_posts','ads_management','ads_read'}<=set(paid['scopes']))
        instagram=configuration({**setup('instagram'),'campaign_access':'publish'})
        self.assertIn('instagram_business_content_publish',instagram['scopes'])
        self.assertEqual(catalog()['instagram']['publication_kinds'],['instagram_reel'])
        self.assertEqual(catalog()['instagram']['publication_connection_provider'],'facebook')
        for provider,mode in [('instagram','ads'),('tiktok','ads'),('linkedin','ads'),('youtube','ads'),('facebook','arbitrary')]:
            with self.subTest(provider=provider,mode=mode),self.assertRaises(Invalid):
                configuration({**setup(provider),'campaign_access':mode})
        self.assertEqual(configuration(setup('facebook')),base)

    def test_native_and_https_callbacks_are_explicit_and_exact(self):
        self.assertEqual(configuration(setup(),4321)['redirect_uri'],'http://127.0.0.1:4321/social/callback/tiktok')
        self.assertEqual(configuration(setup('linkedin',True))['redirect_uri'],'http://127.0.0.1:8765/social/callback/linkedin')
        for change in ({'redirect_uri':'http://evil.example/cb/tiktok'},{'provider':[]},{'version':True},{'client_id':'id&redirect_uri=evil'},
                       {'client_secret':'short'},{'native_enabled':True},{'scope':'publish'}):
            with self.subTest(change=change),self.assertRaises(Invalid):configuration({**setup(),**change})
        for uri in ('http://relay.example/cb/instagram','https://user:password@relay.example/cb/instagram',
                    'https://relay.example/cb/instagram?secret=value','https://relay.example/cb/facebook'):
            with self.subTest(uri=uri),self.assertRaises(Invalid):configuration({**setup('instagram'),'redirect_uri':uri})

    def test_pkce_uses_each_provider_documented_encoding(self):
        verifier='dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
        self.assertEqual(challenge('linkedin',verifier),'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')
        self.assertEqual(challenge('tiktok',verifier),hashlib.sha256(verifier.encode()).hexdigest())
        self.assertNotEqual(challenge('tiktok',verifier),challenge('linkedin',verifier))
        with self.assertRaises(Invalid):challenge('tiktok','too-short')
        with self.assertRaises(Invalid):challenge('facebook',verifier)

    def test_declined_scope_and_malformed_expiry_cannot_look_connected(self):
        self.assertEqual(reported_scopes('profile openid',['openid']),['openid','profile'])
        for value in (None,{},['profile\nforged'],['profile']):
            with self.subTest(value=value),self.assertRaises(Invalid):reported_scopes(value,['openid'])
        for value in (0,-1,True,'86400',10**30):
            with self.subTest(value=value),self.assertRaises(Invalid):seconds(value)
        self.assertEqual(seconds(86400),86400)

    def test_identity_names_retain_unicode_but_deny_spoofing(self):
        self.assertEqual(display('示例团队'),'示例团队');self.assertEqual(account_id(123456), '123456')
        for value in (True,1.5,{},'subject\nother'):
            with self.subTest(value=value),self.assertRaises(Invalid):account_id(value)
        with self.assertRaises(Invalid):display('Example\u202eevil')
        with self.assertRaises(Invalid):reference('not-an-owned-uuid')


if __name__=='__main__':unittest.main()
