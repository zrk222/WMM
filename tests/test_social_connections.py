"""Account confirmation cannot leak credentials, adopt other subjects or race saves."""
import json,time,unittest
from unittest.mock import patch
from mission_control.common import Invalid,canonical
from mission_control.db import connection
from mission_control.social_connections import Connections
from mission_control.social_profiles import Identity
from tests import test_social_flows as flow_fixtures
from tests.test_measurement_connectors import FakeVault


class SocialConnectionTests(unittest.TestCase):
    setUp=flow_fixtures.SocialFlowTests.setUp
    begin=flow_fixtures.SocialFlowTests.begin
    success=flow_fixtures.SocialFlowTests.success
    def confirmed(self):
        started,request=self.begin();self.success(request)
        saved=Connections(self.store).confirm('sample-one',dict(flow_id=started['flow_id'],destination_id='synthetic-user',connection_id='',version=0))
        return saved

    def test_confirmed_account_retains_scoped_grant_and_disconnected_cleanup(self):
        saved=self.confirmed();service=Connections(self.store)
        self.assertEqual(saved['status'],'CONNECTED_READ_TESTED');self.assertEqual(saved['version'],1)
        self.assertNotIn('synthetic-access',canonical(saved));self.assertNotIn('secret_ref',canonical(saved))
        self.assertEqual(service.view('sample-two')['accounts'],[])
        self.assertNotIn('synthetic-access',canonical(self.store.export('sample-one')))
        row=service.get('sample-one',saved['id']);self.assertEqual(service.secrets.load('sample-one','tiktok',row['secret_ref'])['access_token'],'synthetic-access')
        with self.assertRaises(Invalid):service.disconnect('sample-two',saved['id'],1)
        result=service.disconnect('sample-one',saved['id'],1)
        self.assertEqual(result['provider_revocation'],'NOT_PERFORMED');self.assertEqual(len(FakeVault.values),1)
        self.assertEqual(service.get('sample-one',saved['id'])['status'],'DISCONNECTED')

    def test_destination_replay_or_invention_cannot_adopt_or_duplicate_accounts(self):
        started,request=self.begin();self.success(request);service=Connections(self.store)
        body=dict(flow_id=started['flow_id'],destination_id='invented-user',connection_id='',version=0)
        with self.assertRaises(Invalid):service.confirm('sample-one',body)
        saved=service.confirm('sample-one',{**body,'destination_id':'synthetic-user'})
        with self.assertRaises(Invalid):service.confirm('sample-one',{**body,'destination_id':'synthetic-user'})
        started,request=self.begin();self.success(request)
        body={**body,'flow_id':started['flow_id'],'destination_id':'synthetic-user'}
        with self.assertRaisesRegex(Invalid,'already saved'):service.confirm('sample-one',body)
        self.assertEqual(service.get('sample-one',saved['id'])['version'],1)
        reconnected=service.confirm('sample-one',{**body,'connection_id':saved['id'],'version':1})
        self.assertEqual(reconnected['version'],2)

    def test_read_test_requires_same_subject_and_detects_disconnect_race(self):
        saved=self.confirmed();service=Connections(self.store)
        found=Identity('synthetic-user','Updated name',[dict(id='synthetic-user',name='Updated name',kind='PROFILE',tasks=[])],['user.info.basic'])
        with patch('mission_control.social_connections.verify',return_value=found):tested=service.read_test('sample-one',saved['id'],1)
        self.assertEqual(tested['data']['identity']['name'],'Updated name');self.assertEqual(tested['version'],2)
        with patch('mission_control.social_connections.verify',return_value=Identity('other','Other',[],None)):
            with self.assertRaises(Invalid):service.read_test('sample-one',saved['id'],2)
        def raced(*args):service.disconnect('sample-one',saved['id'],2);return found
        with patch('mission_control.social_connections.verify',side_effect=raced):
            with self.assertRaises(Invalid):service.read_test('sample-one',saved['id'],2)
        self.assertEqual(service.get('sample-one',saved['id'])['status'],'DISCONNECTED')

    def test_configuration_change_or_expiry_prevents_read_and_adoption(self):
        saved=self.confirmed();service=Connections(self.store)
        with connection(self.store.path) as db:db.execute('UPDATE social_connections SET expires=? WHERE id=?',(time.time()-1,saved['id']))
        self.assertTrue(service.view('sample-one')['accounts'][0]['reconnect_required'])
        with patch('mission_control.social_connections.verify') as network:
            with self.assertRaises(Invalid):service.read_test('sample-one',saved['id'],1)
            network.assert_not_called()
        started,request=self.begin();self.success(request)
        with connection(self.store.path) as db:db.execute('UPDATE social_configs SET version=version+1 WHERE app_id=? AND provider=?',('sample-one','tiktok'))
        with self.assertRaises(Invalid):service.confirm('sample-one',dict(flow_id=started['flow_id'],destination_id='synthetic-user',connection_id=saved['id'],version=1))
        self.assertEqual(service.get('sample-one',saved['id'])['version'],1)


if __name__=='__main__':unittest.main()
