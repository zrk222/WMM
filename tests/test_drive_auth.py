"""Synthetic Drive protocol boundary checks; no real Google account or credentials."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.error import HTTPError
from mission_control import drive_auth as auth
from mission_control import play_auth, providers
from mission_control.common import Invalid

CONFIG = dict(client_id='123-synthetic.apps.googleusercontent.com', client_secret='synthetic-client-value')
PAYLOAD = dict(access_token='synthetic-access', refresh_token='synthetic-refresh',
               token_type='Bearer', scope=auth.SCOPE, expires_in=3600)


class DriveAuthTests(unittest.TestCase):
    def setUp(self):
        self.state, self.hashed, self.verifier = auth.fresh_state()

    def query(self, **changes):
        fields = dict(state=self.state, code='synthetic-code', scope=auth.SCOPE, picked_file_ids='clip_red,clip_blue')
        fields.update(changes)
        return urlencode(fields)

    def test_configuration_reuses_desktop_parser_without_accepting_other_endpoints(self):
        raw = json.dumps(dict(installed=CONFIG))
        self.assertEqual(auth.configuration(raw), CONFIG)
        for bad in (None, '{}', '\ud800', '{"installed":{},"installed":{}}', json.dumps(dict(web=CONFIG)),
                    json.dumps(dict(installed=dict(CONFIG, token_uri='https://foreign.invalid/token'))),
                    json.dumps(dict(installed=dict(CONFIG, auth_uri='https://foreign.invalid/consent')))):
            with self.subTest(bad=bad), self.assertRaises(Invalid):auth.configuration(bad)
        for bad in ([], None, {}, dict(CONFIG, client_id='foreign-client'), dict(CONFIG, client_secret='bad\nsecret')):
            with self.subTest(bad=bad), self.assertRaises(Invalid):auth.client(bad)

    def test_consent_fixed_selected_file_scope_and_pkce_without_secret_or_verifier(self):
        url = auth.authorization(CONFIG, 8768, self.state, self.verifier)
        parsed = urlsplit(url); query = parse_qs(parsed.query)
        self.assertEqual(parsed._replace(query='').geturl(), 'https://accounts.google.com/o/oauth2/v2/auth')
        expected = dict(scope='https://www.googleapis.com/auth/drive.file', redirect_uri='http://127.0.0.1:8768', prompt='consent',
                        trigger_onepick='true', include_granted_scopes='false', allow_multiple='true',
                        code_challenge_method='S256', code_challenge=play_auth.challenge(self.verifier),
                        state=self.state, response_type='code', access_type='offline', mimetypes=auth.VIDEO_MIMES)
        for key, value in expected.items():self.assertEqual(query[key], [value])
        self.assertNotIn(CONFIG['client_secret'], url); self.assertNotIn(self.verifier, url)
        self.assertNotIn('drive.readonly', url)
        self.assertEqual(self.hashed, hashlib.sha256(self.state.encode()).hexdigest())
        other, _, _ = auth.fresh_state(); self.assertNotEqual(other, self.state)

    def test_consent_rejects_foreign_state_invalid_proof_and_listener(self):
        self.assertEqual(auth.state_value(self.state), self.state)
        for state in ('play_' + 'a'*43, self.state+'x', None, 'drive_'+'é'*43):
            with self.subTest(state=state), self.assertRaises(Invalid):auth.authorization(CONFIG, 8768, state, self.verifier)
        for port in (True, 0, 65536, '8768'):
            with self.subTest(port=port), self.assertRaises(Invalid):auth.authorization(CONFIG, port, self.state, self.verifier)
        for verifier in ('v'*42, 'v'*129, 'v'*43+'\n'):
            with self.subTest(verifier=verifier), self.assertRaises(Invalid):auth.authorization(CONFIG, 8768, self.state, verifier)

    def test_selected_files_exact_one_and24_boundary_preserve_order(self):
        self.assertEqual(auth.selected_files('clip_blue,clip_red'), ['clip_blue','clip_red'])
        values = [('a'*196)+str(i).zfill(4) for i in range(24)]
        self.assertEqual(len(','.join(values)), 4823)
        self.assertEqual(auth.selected_files(','.join(values)), values)
        self.assertEqual(auth.selected_files('x'), ['x'])

    def test_selected_files_rejects_duplicate_excess_url_paths_and_unsupported_shape(self):
        for raw in ('', None, [], 'a,a', 'a,', ',a', 'a'*201, 'file/name', 'file?key=value',
                    'https://drive.google.com/file/x', 'é', 'a b', ','.join('file'+str(i)for i in range(25))):
            with self.subTest(raw=raw), self.assertRaises(Invalid):auth.selected_files(raw)

    def test_success_callback_returns_only_normalized_selection_and_code(self):
        fields = auth.callback_fields(self.query())
        self.assertEqual(set(fields), {'state','code','scope','picked_file_ids'})
        self.assertEqual(fields['picked_file_ids'], 'clip_red,clip_blue')
        value = auth.callback(self.query(authuser='3', prompt='consent'))
        self.assertEqual(value, dict(state=self.state, code='synthetic-code', picked_file_ids=['clip_red','clip_blue']))
        self.assertNotIn('authuser', value); self.assertNotIn('prompt', value)

    def test_callback_rejects_duplicate_raw_and_encoded_keys_and_malformed_query(self):
        queries = [self.query()+'&state='+self.state, self.query()+'&%73tate='+self.state,
                   self.query()+'&code=second', self.query()+'&extra=x', self.query()+'&picked_file_ids=x',
                   self.query()+'&bad=%GG', self.query()+'&bad=%C0%AF', self.query()+'&no_equals',
                   self.query()+'&authuser=1&prompt=a&x=1&y=2&z=3', '', None, 'x'*16385, self.query()+' ']
        for query in queries:
            with self.subTest(query=query), self.assertRaises(Invalid):auth.callback(query)

    def test_callback_rejects_missing_fields_unsafe_code_broad_scope_and_duplicate_files(self):
        values = parse_qs(self.query())
        for key in ('state','code','scope','picked_file_ids'):
            fields={k:v[0] for k,v in values.items() if k!=key}
            with self.subTest(missing=key), self.assertRaises(Invalid):auth.callback(urlencode(fields))
        for update in (dict(code=''),dict(code='x'*4097),dict(code='x\ny'),dict(state='play_'+'x'*43),
                       dict(scope=auth.SCOPE+' https://www.googleapis.com/auth/drive'),dict(picked_file_ids='a,a')):
            with self.subTest(update=update), self.assertRaises(Invalid):auth.callback(self.query(**update))

    def test_cancellation_is_redacted_and_cannot_mix_with_success_fields(self):
        raw=urlencode(dict(state=self.state,error='access_denied',error_description='synthetic-private-value'))
        self.assertEqual(auth.callback(raw),dict(state=self.state,error='access_denied'))
        for raw in (raw+'&code=synthetic-code',raw+'&scope='+auth.SCOPE,
                    urlencode(dict(state=self.state,error='server_error',error_description='synthetic-private-value'))):
            with self.subTest(raw=raw), self.assertRaises(Invalid)as failure:auth.callback(raw)
            self.assertNotIn('synthetic-private-value',str(failure.exception))

    def test_initial_grant_requires_explicit_exact_scope_and_full_refresh_access(self):
        self.assertEqual(auth.grant_scope(PAYLOAD), [auth.SCOPE])
        good=auth.grant(PAYLOAD)
        self.assertEqual(good,dict(access_token='synthetic-access',refresh_token='synthetic-refresh',scopes=[auth.SCOPE],expires_in=3600))
        for key in ('scope','access_token','refresh_token','token_type','expires_in'):
            bad={k:v for k,v in PAYLOAD.items()if k!=key}
            with self.subTest(missing=key),self.assertRaises(Invalid):auth.grant(bad)
        for update in (dict(scope=None),dict(scope=[]),dict(scope=auth.SCOPE+' '+auth.SCOPE),
                       dict(scope='https://www.googleapis.com/auth/drive.readonly'),dict(token_type='bearer'),
                       dict(access_token='private\nvalue'),dict(refresh_token='')):
            with self.subTest(update=update),self.assertRaises(Invalid):auth.grant({**PAYLOAD,**update})

    def test_expiry_exact_integer_boundaries_reject_boolean_and_nonfinite_shapes(self):
        for value in (1,86400):self.assertEqual(auth.grant({**PAYLOAD,'expires_in':value})['expires_in'],value)
        for value in (True,False,0,-1,86401,3600.0,'3600',None,float('inf')):
            with self.subTest(value=value),self.assertRaises(Invalid):auth.grant({**PAYLOAD,'expires_in':value})
        for value in (None,[],False):
            with self.subTest(value=value),self.assertRaises(Invalid):auth.grant(value)

    def test_refresh_retains_verified_fields_rotates_tokens_and_never_expands_scope(self):
        previous=dict(CONFIG,**auth.grant(PAYLOAD)); frozen=copy.deepcopy(previous)
        response=dict(access_token='synthetic-rotated',token_type='Bearer',expires_in=3600)
        with patch.object(auth,'token_request',return_value=response)as call:
            value=auth.refresh(previous)
        self.assertEqual(previous,frozen);self.assertEqual(value['refresh_token'],previous['refresh_token'])
        self.assertEqual(value['scopes'],[auth.SCOPE]);self.assertEqual(call.call_args.args[0]['grant_type'],'refresh_token')
        self.assertNotIn('code',call.call_args.args[0]);self.assertNotIn('scope',call.call_args.args[0])
        rotated=auth.grant({**response,'refresh_token':'synthetic-new-refresh'},previous)
        self.assertEqual(rotated['refresh_token'],'synthetic-new-refresh')
        for payload in ({**response,'scope':None},{**response,'scope':auth.SCOPE+' other'},
                        {**response,'refresh_token':None}):
            with self.subTest(payload=payload),self.assertRaises(Invalid):auth.grant(payload,previous)
        for prior in (None,[],dict(previous,scopes=[]),dict(previous,scopes=[play_auth.SCOPE])):
            with self.subTest(prior=prior),self.assertRaises(Invalid):auth.refresh(prior)

    def test_exchange_uses_one_fixed_post_actual_port_and_original_verifier(self):
        with patch.object(auth,'report_bytes',return_value=json.dumps(PAYLOAD).encode())as call:
            result=auth.exchange(CONFIG,'synthetic-code',self.verifier,8768)
        self.assertEqual(result['scopes'],[auth.SCOPE]);call.assert_called_once()
        request,timeout=call.call_args.args
        self.assertEqual(request.full_url,'https://oauth2.googleapis.com/token');self.assertEqual(request.get_method(),'POST')
        self.assertEqual(timeout,15);fields=parse_qs(request.data.decode())
        self.assertEqual(fields['redirect_uri'],['http://127.0.0.1:8768'])
        self.assertEqual(fields['code_verifier'],[self.verifier]);self.assertEqual(fields['grant_type'],['authorization_code'])
        self.assertEqual(fields['code'],['synthetic-code']);self.assertEqual(fields['client_secret'],[CONFIG['client_secret']])
        self.assertNotIn('scope',fields)

    def test_failed_response_is_not_retried_and_provider_diagnostics_are_redacted(self):
        with patch.object(auth,'report_bytes',side_effect=Invalid('synthetic-private-value'))as call:
            with self.assertRaises(Invalid)as failure:auth.exchange(CONFIG,'synthetic-code',self.verifier,8768)
        call.assert_called_once();self.assertNotIn('synthetic-private-value',str(failure.exception))

    def test_transport_rejects_oversize_duplicate_json_errors_and_non_object_payloads(self):
        for raw in (b'x'*8193,b'{"access_token":"private","access_token":"second"}',
                    b'null',b'[]',b'42',b'\xff',b'['*1500,
                    b'{"error":"invalid_grant","error_description":"synthetic-private-value"}'):
            with self.subTest(raw=raw[:70]),patch.object(auth,'report_bytes',return_value=raw)as call:
                with self.assertRaises(Invalid)as failure:auth.exchange(CONFIG,'synthetic-code',self.verifier,8768)
                self.assertNotIn('synthetic-private-value',str(failure.exception));call.assert_called_once()

    def test_shared_provider_transport_blocks_redirects_without_following_location(self):
        with patch.object(providers,'build_opener')as opener:
            opener.return_value.open.side_effect=HTTPError(auth.TOKEN_ENDPOINT,302,'redirect',{},None)
            with self.assertRaises(Invalid):auth.exchange(CONFIG,'synthetic-code',self.verifier,8768)
        opener.assert_called_once();self.assertIsInstance(opener.call_args.args[0],providers.NoRedirect)
        opener.return_value.open.assert_called_once()
        self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'], 15)

    def test_invalid_code_or_verifier_never_reaches_token_transport(self):
        for code,verifier in (('',self.verifier),('x\ny',self.verifier),('synthetic-code','short')):
            with self.subTest(code=code),patch.object(auth,'report_bytes')as call,self.assertRaises(Invalid):
                auth.exchange(CONFIG,code,verifier,8768)
            call.assert_not_called()
