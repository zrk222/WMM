"""Official provider-shaped fixtures prove protocol differences, never live consent."""
import hashlib,hmac,time,unittest
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.social_auth import fresh_state,authorization,exchange_code,refresh,app_secret_proof
from mission_control.social_tokens import Grant,parse
from mission_control.social_profiles import verify,selected_page
from mission_control.social_registry import PROVIDERS
from mission_control.social_contract import configuration


def config(provider,native=False):
    return dict(provider=provider,client_id='123456',native_enabled=native,
                redirect_uri='http://127.0.0.1:8765/social/callback/'+provider,
                scopes=list(PROVIDERS[provider]['scopes']))


def token(provider='tiktok',**changes):
    result=dict(access_token='synthetic-access',token_type='Bearer',expires_in=3600)
    if provider=='tiktok':result.update(open_id='synthetic-user',scope='user.info.basic',refresh_token='synthetic-refresh',refresh_expires_in=86400)
    return {**result,**changes}


class SocialProviderTests(unittest.TestCase):
    def test_authorize_exact_owner_selected_facebook_permissions(self):
        state,_,verifier=fresh_state()
        body=dict(provider='facebook',client_id='123456',client_secret='synthetic-secret',
                  native_enabled=False,redirect_uri='https://relay.example/cb/facebook',version=0)
        for mode,extra in [('read',[]),('publish',['pages_manage_posts']),
                           ('ads',['pages_manage_posts','ads_management','ads_read'])]:
            selected=configuration({**body,'campaign_access':mode})
            expected=PROVIDERS['facebook']['scopes']+extra
            with self.subTest(mode=mode):
                self.assertEqual(selected['scopes'],expected)
                query=parse_qs(urlsplit(authorization(selected,state,verifier)).query)
                self.assertEqual(query['scope'],[PROVIDERS['facebook']['separator'].join(expected)])
                for scopes in (expected[:-1],expected+['unexpected'],expected+[expected[-1]],list(reversed(expected))):
                    with self.subTest(scopes=scopes),self.assertRaises(Invalid):
                        authorization({**selected,'scopes':scopes},state,verifier)
        for provider in ('instagram','tiktok','linkedin'):
            for mode in ('publish','ads'):
                with self.subTest(provider=provider,mode=mode),self.assertRaises(Invalid):
                    authorization({**config(provider),'campaign_access':mode},state,verifier)
        for mode in ('invalid',None,True,[]):
            with self.subTest(mode=mode),self.assertRaises(Invalid):
                authorization({**config('facebook'),'campaign_access':mode},state,verifier)
        with patch('mission_control.social_auth.request') as request:
            with self.assertRaises(Invalid):
                exchange_code({**config('facebook'),'scopes':['unexpected']},'synthetic-secret','synthetic-code',verifier)
            request.assert_not_called()

    def test_authorize_uses_provider_specific_pkce_without_secret(self):
        state,digest,verifier=fresh_state()
        self.assertEqual(digest,hashlib.sha256(state.encode()).hexdigest())
        for provider in PROVIDERS:
            url=authorization(config(provider),state,verifier);query=parse_qs(urlsplit(url).query)
            self.assertNotIn('client_secret',query);self.assertEqual(query['state'],[state])
            self.assertEqual('code_challenge' in query,provider=='tiktok')
            if provider=='tiktok':self.assertEqual(query['code_challenge'],[hashlib.sha256(verifier.encode()).hexdigest()])
        native=authorization(config('linkedin',True),state,verifier)
        self.assertIn('/oauth/native-pkce/authorization?',native)
        self.assertNotIn('=',parse_qs(urlsplit(native).query)['code_challenge'][0])
        broken=config('linkedin');broken['scopes']=['w_member_social']
        with self.assertRaises(Invalid):authorization(broken,state,verifier)

    def test_instagram_short_exchange_is_multipart_then_long_and_subject_preserved(self):
        responses=[dict(access_token='synthetic-short',user_id=1234,permissions=['instagram_business_basic']),
                   token('instagram',access_token='synthetic-long',expires_in=5184000)]
        with patch('mission_control.social_auth.request',side_effect=responses) as request:
            grant=exchange_code(config('instagram'),'synthetic-secret','synthetic-code','V'*64)
        self.assertEqual([call.args[1] for call in request.call_args_list],['code','long'])
        self.assertEqual(grant.facts['subject_id'],'1234');self.assertEqual(grant.credentials,{'access_token':'synthetic-long'})
        self.assertEqual(grant.facts['reported_scopes'],['instagram_business_basic'])
        self.assertEqual(grant.facts['renewal'],'LONG_LIVED_TOKEN_REFRESH')

    def test_facebook_long_exchange_and_linkedin_native_do_not_mix_grants(self):
        with patch('mission_control.social_auth.request',side_effect=[token('facebook'),token('facebook',expires_in=5184000)]) as request:
            grant=exchange_code(config('facebook'),'synthetic-secret','synthetic-code','V'*64)
        self.assertEqual([call.args[1] for call in request.call_args_list],['code','long'])
        self.assertEqual(grant.facts['renewal'],'OFFICIAL_REAUTHORIZATION')
        with patch('mission_control.social_auth.request',return_value=token('linkedin')) as request:
            exchange_code(config('linkedin',True),'','synthetic-code','V'*64)
        self.assertEqual(request.call_args.args[1],'code_native')
        self.assertNotIn('client_secret',request.call_args.args[2])

    def test_facebook_selected_permissions_follow_token_and_inspection(self):
        selected={**config('facebook'),'campaign_access':'publish',
                  'scopes':PROVIDERS['facebook']['scopes']+['pages_manage_posts']}
        with patch('mission_control.social_auth.request',side_effect=[token('facebook'),token('facebook')]):
            grant=exchange_code(selected,'synthetic-secret','synthetic-code','V'*64)
        self.assertEqual(grant.facts['requested_scopes'],selected['scopes'])
        self.assertIsNone(grant.facts['reported_scopes'])
        with patch('mission_control.social_auth.request',return_value=token('facebook',scope=' '.join(PROVIDERS['facebook']['scopes']))):
            with self.assertRaises(Invalid):exchange_code(selected,'synthetic-secret','synthetic-code','V'*64)
        def responses(inspected,granted):
            return [dict(access_token='synthetic-app-access'),
                    dict(data=dict(is_valid=True,app_id='123456',user_id='123',scopes=inspected,expires_at=int(time.time())+3600)),
                    dict(id='123',name='Synthetic person'),
                    dict(data=[dict(permission=s,status='granted') for s in granted]),dict(data=[])]
        for mode,extra in [('publish',['pages_manage_posts']),('ads',['pages_manage_posts','ads_management','ads_read'])]:
            required=PROVIDERS['facebook']['scopes']+extra
            current={**selected,'campaign_access':mode,'scopes':required}
            with patch('mission_control.social_profiles.request',side_effect=responses(required,required)):
                self.assertEqual(set(verify(current,'synthetic-secret',grant).permissions),set(required))
            for inspected,granted in [(required[:-1],required),(required,required[:-1])]:
                with self.subTest(mode=mode,inspected=inspected,granted=granted):
                    with patch('mission_control.social_profiles.request',side_effect=responses(inspected,granted)):
                        with self.assertRaises(Invalid):verify(current,'synthetic-secret',grant)

    def test_token_scope_lifetime_wrapper_and_subject_validation(self):
        for value in (token(scope='video.publish'),token(expires_in=True),token(token_type='MAC'),
                      {'access_token':'x','data':[token()]},{'data':[token(),token()]}):
            with self.subTest(value=value),self.assertRaises(Invalid):parse('tiktok',value,1000)
        self.assertEqual(parse('tiktok',{'data':[token()]},1000).facts['subject_id'],'synthetic-user')
        with self.assertRaises(Invalid):parse('instagram',{'access_token':'short','user_id':True},1000,short=True)

    def test_tiktok_rotation_is_retained_and_subject_drift_rejected(self):
        clock=time.time();old=parse('tiktok',token(),clock)
        with patch('mission_control.social_auth.request',return_value=token(refresh_token='synthetic-rotated')):
            new=refresh(config('tiktok'),'synthetic-secret',old.credentials,old.facts)
        self.assertEqual(new.credentials['refresh_token'],'synthetic-rotated')
        with patch('mission_control.social_auth.request',return_value=token(open_id='other-user')):
            with self.assertRaises(Invalid):refresh(config('tiktok'),'synthetic-secret',old.credentials,old.facts)

    def test_linkedin_refresh_does_not_extend_fixed_window_or_drop_old_token(self):
        clock=time.time();old=parse('linkedin',token('linkedin',refresh_token='synthetic-refresh',refresh_token_expires_in=7200),clock)
        with patch('mission_control.social_auth.request',return_value=token('linkedin',refresh_token_expires_in=99999)):
            new=refresh(config('linkedin'),'synthetic-secret',old.credentials,old.facts)
        self.assertEqual(new.credentials['refresh_token'],'synthetic-refresh')
        self.assertEqual(new.facts['refresh_expires_at'],old.facts['refresh_expires_at'])
        with patch('mission_control.social_auth.request') as request:
            for cfg,facts,creds in ((config('linkedin',True),old.facts,old.credentials),
                                    (config('linkedin'),old.facts,{'access_token':'synthetic-access'}),
                                    (config('facebook'),old.facts,old.credentials)):
                with self.assertRaises(Invalid):refresh(cfg,'synthetic-secret',creds,facts)
            request.assert_not_called()

    def test_instagram_renewal_age_and_expiry_require_reauthorization(self):
        clock=time.time();old=parse('instagram',token('instagram',expires_in=5184000),clock)
        with patch('mission_control.social_auth.request') as request:
            with self.assertRaises(Invalid):refresh(config('instagram'),'synthetic-secret',old.credentials,old.facts)
            with self.assertRaises(Invalid):refresh(config('instagram'),'synthetic-secret',old.credentials,{**old.facts,'expires_at':clock-1})
            request.assert_not_called()
        facts={**old.facts,'issued_at':clock-86401,'subject_id':'1234'}
        with patch('mission_control.social_auth.request',return_value=token('instagram')) as request:
            new=refresh(config('instagram'),'synthetic-secret',old.credentials,facts)
        self.assertEqual(new.facts['subject_id'],'1234');self.assertEqual(request.call_args.args[1],'refresh')

    def test_profile_verification_strips_unneeded_fields_and_checks_subject(self):
        grant=parse('tiktok',token(),time.time())
        raw=dict(data={'user':dict(open_id='synthetic-user',display_name='Synthetic account',email='not-retained')},error={'code':'ok'})
        with patch('mission_control.social_profiles.request',return_value=raw):identity=verify(config('tiktok'),'synthetic-secret',grant)
        self.assertEqual(identity.subject_id,'synthetic-user');self.assertNotIn('email',str(identity))
        raw['data']['user']['open_id']='other'
        with patch('mission_control.social_profiles.request',return_value=raw):
            with self.assertRaises(Invalid):verify(config('tiktok'),'synthetic-secret',grant)
        with patch('mission_control.social_profiles.request',return_value=dict(sub='member',name='Synthetic member',email='discard')):
            identity=verify(config('linkedin'),'synthetic-secret',Grant({'access_token':'synthetic-access'},{'reported_scopes':None}))
        self.assertEqual(identity.destinations[0]['id'],'member');self.assertIsNone(identity.permissions)
        self.assertNotIn('discard',str(identity))

    def test_instagram_profile_requires_professional_identity_not_app_scoped_id(self):
        grant=Grant({'access_token':'synthetic-access'},{'subject_id':'1234','reported_scopes':['instagram_business_basic']})
        raw=dict(id='5678',user_id='1234',username='synthetic_creator',account_type='MEDIA_CREATOR')
        with patch('mission_control.social_profiles.request',return_value={'data':[raw]}):identity=verify(config('instagram'),'synthetic-secret',grant)
        self.assertEqual(identity.subject_id,'1234');self.assertEqual(identity.destinations[0]['app_scoped_id'],'5678')
        for changed in ({'account_type':'PERSONAL'},{'user_id':'5678'}):
            with patch('mission_control.social_profiles.request',return_value={**raw,**changed}):
                with self.assertRaises(Invalid):verify(config('instagram'),'synthetic-secret',grant)

    def test_facebook_inspects_app_permissions_and_sanitizes_owned_pages(self):
        permissions=list(PROVIDERS['facebook']['scopes'])
        data=[dict(access_token='synthetic-app-access'),
              dict(data=dict(is_valid=True,app_id='123456',user_id='123',scopes=permissions,expires_at=int(time.time())+3600)),
              dict(id='123',name='Synthetic person'),
              dict(data=[dict(permission=scope,status='granted') for scope in permissions]),
              dict(data=[dict(id='456',name='Synthetic Page',tasks=['ANALYZE'],access_token='synthetic-page-access')])]
        with patch('mission_control.social_profiles.request',side_effect=data) as request:
            identity=verify(config('facebook'),'synthetic-secret',Grant({'access_token':'synthetic-access'},{}))
        self.assertEqual(identity.destinations,[dict(id='456',name='Synthetic Page',kind='PAGE',tasks=['ANALYZE'])])
        self.assertNotIn('synthetic-page-access',str(identity))
        self.assertIn('appsecret_proof',request.call_args_list[2].args[2])
        data[1]['data']['app_id']='other'
        with patch('mission_control.social_profiles.request',side_effect=data):
            with self.assertRaises(Invalid):verify(config('facebook'),'synthetic-secret',Grant({'access_token':'synthetic-access'},{}))

    def test_page_selection_rechecks_access_and_follows_cursor_not_next_url(self):
        first=dict(data=[],paging=dict(next='https://attacker.invalid/credential-trap',cursors={'after':'safe-cursor'}))
        page=dict(id='456',name='Synthetic Page',tasks=['ANALYZE'],access_token='synthetic-page-access')
        with patch('mission_control.social_profiles.request',side_effect=[first,dict(data=[page]),dict(id='456',name='Renamed Page')]) as request:
            public,secret=selected_page('synthetic-secret','synthetic-access','456')
        self.assertEqual(request.call_args_list[1].args[2]['after'],'safe-cursor')
        self.assertEqual(secret,'synthetic-page-access');self.assertNotIn('access_token',public)
        self.assertEqual(public['name'],'Renamed Page')
        self.assertEqual(app_secret_proof('synthetic-access','synthetic-secret'),hmac.new(b'synthetic-secret',b'synthetic-access',hashlib.sha256).hexdigest())
        with patch('mission_control.social_profiles.request',return_value=first):
            with self.assertRaises(Invalid):selected_page('synthetic-secret','synthetic-access','456')


if __name__=='__main__':unittest.main()
