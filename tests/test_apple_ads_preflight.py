"""Current Apple Ads preflight protocol and strict inventory isolation; synthetic only."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.apple_ads_preflight import ENDPOINT, numeric_id, inventory_request, shape_inventory
from mission_control.providers import sync
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once
from tests.test_provider_reports import campaign


def page(rows=None,total=None):
    rows=[campaign()] if rows is None else rows
    return {"result":rows,"pagination":{"offset":0,"pageSize":100,"totalCount":len(rows) if total is None else total}}


class AppleAdsPreflight(unittest.TestCase):
    def setUp(self):
        self.binding={"provider":"apple_ads","env_ref":"GROWTH_SAMPLE_ONE_PREFLIGHT_TOKEN","store_app_id":"123","account_id":"456"}
        self.env=patch.dict(os.environ,{self.binding["env_ref"]:"synthetic-bearer"});self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_inventory_request_and_sync_use_current_scoped_protocol(self):
        store,account,body=inventory_request(self.binding)
        self.assertEqual((store,account),("123","456"))
        self.assertEqual(body,{"filters":[{"field":"promotedObjectType","operator":"EQUALS","value":"APPSTORE_APP"},{"field":"promotedObjectId","operator":"EQUALS","value":"123"}],"pagination":{"offset":0,"pageSize":100,"fetchTotalCount":True}})
        with patch('mission_control.providers.report_request',return_value=page()) as request,patch('mission_control.providers.read_json') as legacy:
            result=sync(self.binding,'sample-one')
        request.assert_called_once_with(ENDPOINT,{"Authorization":"Bearer synthetic-bearer","X-AP-Context":"adAccountId=456"},body)
        legacy.assert_not_called()
        self.assertEqual(result['api_version'],'PLATFORM_V1')
        self.assertEqual(result['campaign_ids'],['42'])
        self.assertEqual(result['coverage'],'COMPLETE')
        self.assertFalse(result['external_writes'])
        self.assertEqual(len(result['source_hash']),64)
        self.assertNotIn('synthetic-bearer',json.dumps(result))
        self.assertNotIn('api.searchads.apple.com',json.dumps(result))

    def test_numeric_id_rejects_url_syntax_unicode_bool_and_oversize(self):
        self.assertEqual(numeric_id(42,'id'),'42')
        for value in [None,True,-1,1.5,'../123','１２３','١٢٣','123 ','9'*31]:
            with self.subTest(value=value),self.assertRaises(Invalid):numeric_id(value,'id')
        for key in ('store_app_id','account_id'):
            with patch('mission_control.providers.credential') as secret,patch('mission_control.providers.report_request') as network,self.assertRaises(Invalid):
                sync({**self.binding,key:'../invalid'},'sample-one')
            secret.assert_not_called();network.assert_not_called()

    def test_shape_inventory_preserves_empty_partial_and_current_identity_limits(self):
        empty=shape_inventory(page([]),'123','456')
        self.assertEqual(empty['identity_proof'],'NO_CAMPAIGN_IDENTITY_PROOF')
        self.assertEqual(empty['campaign_ids'],[])
        self.assertEqual(empty['coverage'],'COMPLETE')
        partial=shape_inventory(page(total=150),'123','456')
        self.assertEqual(partial['coverage'],'PARTIAL')
        self.assertEqual((partial['returned_count'],partial['total_count']),(1,150))
        self.assertEqual(partial['identity_proof'],'RETURNED_CAMPAIGNS_MATCH_APP_AND_ACCOUNT')
        self.assertEqual(shape_inventory(page([campaign(str(i)) for i in range(100)]),'123','456')['returned_count'],100)

    def test_shape_inventory_rejects_other_app_account_brand_and_duplicates(self):
        for row in [campaign(app='999'),campaign(account='999'),dict(campaign(),promotedObjectType='BUSINESS_BRAND'),dict(campaign(),id=True),None]:
            with self.subTest(row=row),self.assertRaises(Invalid):shape_inventory(page([row]),'123','456')
        with self.assertRaisesRegex(Invalid,'duplicate'):
            shape_inventory(page([campaign(),campaign()]),'123','456')
        other=dict(campaign(app='999'),name='Private other app campaign')
        with self.assertRaises(Invalid) as error:shape_inventory(page([other]),'123','456')
        self.assertNotIn(other['name'],str(error.exception))

    def test_pagination_numbers_and_validate_page_reject_ambiguous_boundaries(self):
        cases=[None,[],{},dict(page(),result={}),page([campaign(str(i)) for i in range(101)]),dict(page(),pagination=None)]
        for key,value in [('offset',1),('offset',False),('pageSize',101),('pageSize',0),('pageSize',-1),('totalCount',0),('totalCount',True)]:
            invalid=page();invalid['pagination'][key]=value;cases.append(invalid)
        cases.append(page([],1))
        for value in cases:
            with self.subTest(value=value),self.assertRaises(Invalid):shape_inventory(value,'123','456')
        self.assertEqual(shape_inventory({'result':[],'pagination':{'offset':0,'pageSize':0,'totalCount':0}},'123','456')['coverage'],'COMPLETE')

    def test_shared_transport_stays_read_only_bounded_and_redirect_safe(self):
        with patch('mission_control.providers.build_opener') as opener:
            response=opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value=json.dumps(page()).encode()
            result=sync(self.binding,'sample-one')
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,ENDPOINT);self.assertEqual(request.method,'POST')
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],15)
            response.read.assert_called_once_with(2097153)
            self.assertEqual(result['payload']['data'][0]['id'],42)
            response.read.return_value=b'{bad'
            with self.assertRaises(Invalid):sync(self.binding,'sample-one')
        with patch.dict(os.environ,{},clear=True),patch('mission_control.providers.report_request') as network,self.assertRaises(Invalid):sync(self.binding,'sample-one')
        network.assert_not_called()

    def test_worker_preserves_failed_binding_recovers_and_rejects_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'qa.sqlite');service=Service(store)
            record=service.evidence('sample-one',{'kind':'connection','title':'Synthetic Ads reader','source':'Synthetic fixture','data':self.binding})
            body={'action':'sync','data':{'connection_id':record['id']},'request_key':'failed-preflight'}
            service.queue('sample-one',body)
            with patch('mission_control.providers.report_request',side_effect=Invalid('Synthetic provider denied access')):run_once(store)
            self.assertEqual(service.workspace('sample-one')['jobs'][0]['status'],'BLOCKED')
            self.assertEqual(store.records('sample-one')[0],record)
            service.queue('sample-one',{**body,'request_key':'recovered-preflight'})
            with patch('mission_control.providers.report_request',return_value=page()):run_once(store)
            self.assertEqual(service.workspace('sample-one')['jobs'][0]['result']['campaign_ids'],['42'])
            with self.assertRaises(Invalid):service.queue('sample-two',{**body,'request_key':'other-app'})
            service.queue('sample-one',{**body,'request_key':'rotating-preflight'})
            def rotated(*args):
                store.save_record('sample-one',{**record,'title':'Rotated during read'})
                return page()
            with patch('mission_control.providers.report_request',side_effect=rotated):run_once(store)
            result=service.workspace('sample-one')['jobs'][0]
            self.assertEqual(result['status'],'BLOCKED')
            self.assertNotIn('Synthetic campaign',json.dumps(result))
            self.assertIn('Connection changed',result['result']['error'])


if __name__=='__main__':unittest.main()
