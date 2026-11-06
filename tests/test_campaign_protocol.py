"""Fixed Meta request vocabulary from the official AdsInsights SDK contract."""
import unittest
from unittest.mock import patch
from uuid import UUID
from mission_control.campaign_contract import REEL_SCHEMA, reel_data
from mission_control.campaign_transport import MetaTransport,Unconfirmed
from mission_control.common import Invalid, digest
from mission_control.social_registry import META_VERSION


class CampaignProtocolTests(unittest.TestCase):
    def test_campaign_read_requests_configured_and_effective_status_together(self):
        transport=MetaTransport()
        with patch.object(transport,'request',return_value={'id':'123'}) as request:
            transport.read_paid('campaign','123','synthetic-token','synthetic-secret',lambda:None)
        self.assertEqual(request.call_args.args[0],'GET')
        self.assertIn('effective_status',request.call_args.args[2]['fields'].split(','))

    def test_reel_request_binds_exact_caption_and_all_effect_identities(self):
        body = dict(schema=REEL_SCHEMA, request_id=str(UUID(int=1)),
                    app_id='sample-one', page_id='123', policy_id=str(UUID(int=2)),
                    policy_hash='a' * 64, admission_id=str(UUID(int=3)),
                    admission_hash='b' * 64, artifact_id=str(UUID(int=4)),
                    artifact_sha256='c' * 64, rights_hashes=['e' * 64, 'd' * 64],
                    caption='  Try one useful next step.\nYour choice. 🎬  ')
        result = reel_data(body)
        self.assertEqual(result['caption'], body['caption'])
        self.assertEqual(result['rights_hashes'], ['d' * 64, 'e' * 64])
        self.assertEqual(digest(result), digest(reel_data(dict(body, rights_hashes=result['rights_hashes']))))
        for key, replacement in [('caption', 'Changed'), ('page_id', '456'),
                                 ('policy_hash', 'f' * 64), ('admission_hash', 'f' * 64),
                                 ('artifact_sha256', 'f' * 64), ('rights_hashes', ['f' * 64])]:
            with self.subTest(key=key):
                self.assertNotEqual(digest(result), digest(reel_data(dict(body, **{key: replacement}))))
        for key, invalid in [('schema', 'unknown'), ('app_id', '../other'), ('page_id', 'me'),
                             ('request_id', 'arbitrary'), ('policy_hash', 'A' * 64),
                             ('rights_hashes', []), ('rights_hashes', ['d' * 64] * 2),
                             ('caption', ' '), ('caption', 'x' * 5001), ('caption', 'bad\x00')]:
            with self.subTest(key=key, invalid=str(invalid)[:25]), self.assertRaises(Invalid):
                reel_data(dict(body, **{key: invalid}))
        for extra in ('upload_url', 'ad_account_id', 'approved', 'token'):
            with self.subTest(extra=extra), self.assertRaises(Invalid):
                reel_data(dict(body, **{extra: 'synthetic'}))

    def test_insights_uses_supported_maximum_preset_not_lifetime(self):
        transport=MetaTransport()
        with patch.object(transport,'request',return_value={'data':[{'spend':'12.34'}]}) as request:
            result=transport.ad_insights('123','synthetic-token','synthetic-secret',lambda:None)
        args=request.call_args.args
        self.assertEqual(args[0],'GET');self.assertEqual(args[1],'/'+META_VERSION+'/123/insights')
        self.assertEqual(args[2]['date_preset'],'maximum');self.assertEqual(args[2]['fields'],'spend')
        self.assertEqual(result['reported_spend'],'12.34')
        self.assertEqual(result['reporting'],'PROVIDER_REPORTED_MAY_LAG')

    def test_missing_spend_stays_unknown_and_malformed_reports_are_rejected(self):
        transport=MetaTransport()
        with patch.object(transport,'request',return_value={'data':[]}):
            self.assertIsNone(transport.ad_insights('123','synthetic-token','synthetic-secret',lambda:None)['reported_spend'])
        for rows in ([{'spend':'NaN'}],[{'spend':1.23}],[{'spend':'1'},{'spend':'2'}],None):
            with self.subTest(rows=rows),patch.object(transport,'request',return_value={'data':rows}),self.assertRaises(Unconfirmed):
                transport.ad_insights('123','synthetic-token','synthetic-secret',lambda:None)


if __name__=='__main__':unittest.main()
