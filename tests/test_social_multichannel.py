import unittest
from urllib.parse import parse_qs, urlsplit
from mission_control.common import Invalid
from mission_control.social_contract import configuration, challenge, reported_scopes
from mission_control.social_auth import authorization, code_fields, validated_scopes, refresh_fields
from mission_control.social_registry import catalog


def setup(provider, mode='read'):
    return dict(provider=provider, client_id=('123456' if provider in ('facebook','instagram') else '123456789-abc.apps.googleusercontent.com' if provider=='youtube' else 'test-client'), client_secret='test-client-secret', redirect_uri='https://relay.example/cb/'+provider if provider!='tiktok' else '', native_enabled=False, version=0, campaign_access=mode)

class MultichannelConsent(unittest.TestCase):
    def test_requested_scopes_and_stale_config(self):
        required={'instagram':'instagram_business_content_publish','tiktok':'video.publish','linkedin':'w_member_social','youtube':'https://www.googleapis.com/auth/youtube.upload'}
        for provider,scope in required.items():
            with self.subTest(provider=provider):
                default=configuration(setup(provider)); published=configuration(setup(provider,'publish'))
                self.assertNotIn(scope,default['scopes']); self.assertIn(scope,published['scopes'])
                self.assertEqual(validated_scopes(published),published['scopes'])
                with self.assertRaises(Invalid): validated_scopes({**published,'scopes':default['scopes']})
                with self.assertRaises(Invalid): reported_scopes(default['scopes'],published['scopes'])
                with self.assertRaises(Invalid): configuration(setup(provider,'ads'))
                self.assertTrue(catalog()[provider]['publishing_implemented'])
                self.assertTrue(catalog()[provider]['publication_kinds'])
        self.assertIn('video.list',configuration(setup('tiktok','publish'))['scopes'])
        self.assertIn('pages_manage_posts',configuration(setup('facebook','publish'))['scopes'])
        self.assertIn('ads_management',configuration(setup('facebook','ads'))['scopes'])

    def test_google_pkce_and_client_boundary(self):
        cfg=configuration(setup('youtube','publish')); verifier='dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
        self.assertEqual(challenge('youtube',verifier),'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')
        params=parse_qs(urlsplit(authorization(cfg,'s'*43,verifier)).query)
        self.assertEqual(params['access_type'],['offline']); self.assertEqual(params['include_granted_scopes'],['false']); self.assertEqual(params['prompt'],['consent'])
        self.assertEqual(params['code_challenge_method'],['S256'])
        self.assertEqual(code_fields(cfg,'test-client-secret','code',verifier)[0]['code_verifier'],verifier)
        self.assertEqual(reported_scopes(' '.join(cfg['scopes']),cfg['scopes']),sorted(cfg['scopes']))
        for client in ('evil.example','x.apps.googleusercontent.com.evil','x/apps.googleusercontent.com','x&redirect_uri=evil'):
            with self.subTest(client=client),self.assertRaises(Invalid):configuration({**setup('youtube'),'client_id':client})
        self.assertEqual(refresh_fields(cfg,'test-client-secret',{'refresh_token':'token'},{},0)['refresh_token'],'token')

if __name__ == '__main__': unittest.main()
