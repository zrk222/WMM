"""YouTube grant and channel contracts; no live provider access."""
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.social_tokens import Grant, parse
from mission_control.social_profiles import verify
from mission_control.social_transport import OPERATIONS, parameters
from mission_control.social_auth import refresh

READ = 'https://www.googleapis.com/auth/youtube.readonly'
UPLOAD = 'https://www.googleapis.com/auth/youtube.upload'


class YouTubeConnectionTests(unittest.TestCase):
    def test_reported_scopes_and_refresh_facts_are_not_invented(self):
        raw = {'access_token':'access', 'token_type':'Bearer', 'expires_in':3600,
               'refresh_token':'refresh', 'scope':READ + ' ' + UPLOAD}
        grant = parse('youtube', raw, 100, requested_scopes=[READ, UPLOAD])
        self.assertEqual(grant.facts['reported_scopes'], sorted([READ, UPLOAD]))
        self.assertEqual(grant.facts['renewal'], 'REFRESH_TOKEN')
        renewed = parse('youtube', {'access_token':'new','expires_in':3600}, 200,
                        prior=grant.facts, requested_scopes=[READ, UPLOAD])
        self.assertEqual(renewed.facts['reported_scopes'], grant.facts['reported_scopes'])
        unknown = parse('youtube', {'access_token':'access','expires_in':3600}, 100,
                        requested_scopes=[READ, UPLOAD])
        self.assertIsNone(unknown.facts['reported_scopes'])
        with self.assertRaises(Invalid):
            parse('youtube', {**raw, 'scope':READ}, 100, requested_scopes=[READ, UPLOAD])

    def test_single_provider_channel_and_stable_identity(self):
        grant = Grant({'access_token':'secret'}, {'reported_scopes':[READ], 'subject_id':None})
        payload = {'kind':'youtube#channelListResponse', 'items':[{'id':'UCabc-123', 'snippet':{'title':'My channel'}}]}
        with patch('mission_control.social_profiles.request', return_value=payload) as call:
            found = verify({'provider':'youtube'}, '', grant)
        self.assertEqual(found.subject_id, 'UCabc-123')
        self.assertEqual(found.destinations[0]['id'], 'UCabc-123')
        self.assertEqual(call.call_args.kwargs['bearer'], 'secret')
        with patch('mission_control.social_profiles.request', return_value=payload):
            with self.assertRaises(Invalid):
                verify({'provider':'youtube'}, '', Grant(grant.credentials, {**grant.facts, 'subject_id':'different'}))

    def test_missing_multiple_and_paginated_channels_fail_closed(self):
        grant = Grant({'access_token':'secret'}, {'reported_scopes':[READ], 'subject_id':None})
        item = {'id':'UCabc', 'snippet':{'title':'Channel'}}
        for payload in ({'items':[]}, {'items':[item,item]}, {'items':[item], 'nextPageToken':'next'}, {'items':[{'id':'bad'}]}):
            with self.subTest(payload=payload), patch('mission_control.social_profiles.request', return_value=payload):
                with self.assertRaises(Invalid): verify({'provider':'youtube'}, '', grant)

    def test_transport_is_fixed_to_google(self):
        spec=OPERATIONS[('youtube','identity')]
        url, fields=parameters(spec,{})
        self.assertEqual(url,'https://www.googleapis.com/youtube/v3/channels')
        self.assertEqual(fields,{'part':'id,snippet','mine':'true'})
        with self.assertRaises(Invalid): parameters(spec,{'mine':'false'})

    def test_refresh_preserves_or_rotates_provider_refresh_token(self):
        config={'provider':'youtube','client_id':'client','native_enabled':False, 'campaign_access':'publish',
                'scopes':[READ,UPLOAD]}
        facts={'provider':'youtube','subject_id':'UCabc','expires_at':9999999999,
               'refresh_expires_at':None,'reported_scopes':[READ,UPLOAD]}
        credentials={'access_token':'old','refresh_token':'old-refresh'}
        with patch('mission_control.social_auth.request', return_value={'access_token':'new','expires_in':3600}):
            result=refresh(config,'client-secret',credentials,facts)
        self.assertEqual(result.credentials['refresh_token'],'old-refresh')
        self.assertEqual(result.facts['reported_scopes'],[READ,UPLOAD])
        self.assertEqual(result.facts['renewal'],'REFRESH_TOKEN')
        with patch('mission_control.social_auth.request', return_value={'access_token':'new','expires_in':3600,'refresh_token':'rotated'}):
            result=refresh(config,'client-secret',credentials,facts)
        self.assertEqual(result.credentials['refresh_token'],'rotated')


if __name__ == '__main__': unittest.main()
