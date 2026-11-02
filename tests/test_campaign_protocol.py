"""Fixed Meta request vocabulary from the official AdsInsights SDK contract."""
import unittest
from unittest.mock import patch
from mission_control.campaign_transport import MetaTransport,Unconfirmed
from mission_control.social_registry import META_VERSION


class CampaignProtocolTests(unittest.TestCase):
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
