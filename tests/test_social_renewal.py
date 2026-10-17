"""Only owned refreshes adopt tokens; interruption and drift require reauthorization."""
import time,unittest
from unittest.mock import patch
from mission_control.common import Invalid,canonical
from mission_control.db import connection
from mission_control.social_connections import Connections
from mission_control.social_renewal import Renewal
from mission_control.social_tokens import parse
from mission_control.social_profiles import Identity
from tests import test_social_connections as fixtures
from tests.test_social_providers import token


class SocialRenewalTests(unittest.TestCase):
    setUp=fixtures.SocialConnectionTests.setUp
    begin=fixtures.SocialConnectionTests.begin
    success=fixtures.SocialConnectionTests.success
    confirmed=fixtures.SocialConnectionTests.confirmed

    def responses(self):
        grant=parse('tiktok',token(access_token='synthetic-renewed',refresh_token='synthetic-rotated'),time.time())
        found=Identity('synthetic-user','Synthetic person',[dict(id='synthetic-user',name='Synthetic person',kind='PROFILE',tasks=[])],['user.info.basic'])
        return grant,found

    def test_successful_rotation_adopts_only_after_identity_check(self):
        saved=self.confirmed();renewal=Renewal(self.store);grant,found=self.responses()
        old=renewal.accounts.get('sample-one',saved['id'])
        with patch('mission_control.social_renewal.refresh',return_value=grant),patch('mission_control.social_renewal.verify',return_value=found):result=renewal.run('sample-one',saved['id'],1)
        self.assertEqual(result['status'],'CONNECTED_READ_TESTED');self.assertEqual(result['version'],2)
        new=renewal.accounts.get('sample-one',saved['id']);self.assertNotEqual(old['secret_ref'],new['secret_ref'])
        self.assertEqual(renewal.accounts.secrets.load('sample-one','tiktok',new['secret_ref'])['refresh_token'],'synthetic-rotated')
        with self.assertRaises(Invalid):renewal.accounts.secrets.load('sample-one','tiktok',old['secret_ref'])

    def test_only_one_owner_and_expired_lease_is_not_replayed_after_restart(self):
        saved=self.confirmed();renewal=Renewal(self.store);row,lease=renewal.claim('sample-one',saved['id'],1)
        with self.assertRaises(Invalid):renewal.claim('sample-one',saved['id'],1)
        with connection(self.store.path) as db:db.execute('UPDATE social_connections SET lease_until=? WHERE id=?',(time.time()-1,saved['id']))
        self.assertEqual(Renewal(self.store).recover(),1)
        current=renewal.accounts.get('sample-one',saved['id']);self.assertEqual(current['status'],'RECONNECT_REQUIRED')
        with patch('mission_control.social_renewal.refresh') as network:
            self.assertFalse(renewal.tick());network.assert_not_called()
        with self.assertRaises(Invalid):renewal.accounts.read_test('sample-one',saved['id'],current['version'])
        self.assertEqual(renewal.accounts.secrets.load('sample-one','tiktok',current['secret_ref'])['access_token'],'synthetic-access')

    def test_ambiguous_refresh_does_not_replay_or_expose_error(self):
        saved=self.confirmed();renewal=Renewal(self.store)
        with patch('mission_control.social_renewal.refresh',side_effect=OSError('PRIVATE_TOKEN_MUST_NOT_SURFACE')) as network:
            result=renewal.run('sample-one',saved['id'],1)
            self.assertFalse(renewal.tick());self.assertEqual(network.call_count,1)
        self.assertEqual(result['status'],'RECONNECT_REQUIRED');self.assertNotIn('PRIVATE',canonical(result))

    def test_changed_subject_or_disconnect_race_cannot_replace_access(self):
        saved=self.confirmed();renewal=Renewal(self.store);grant,found=self.responses()
        with patch('mission_control.social_renewal.refresh',return_value=grant),patch('mission_control.social_renewal.verify',return_value=Identity('other','Other',[],None)):
            result=renewal.run('sample-one',saved['id'],1)
        self.assertEqual(result['status'],'RECONNECT_REQUIRED')
        row=renewal.accounts.get('sample-one',saved['id']);self.assertEqual(renewal.accounts.secrets.load('sample-one','tiktok',row['secret_ref'])['access_token'],'synthetic-access')
        other=self.confirmed_account_after_disconnect(saved['id'],row['version'])
        def raced(*args):renewal.accounts.disconnect('sample-one',other['id'],other['version']);return found
        with patch('mission_control.social_renewal.refresh',return_value=grant),patch('mission_control.social_renewal.verify',side_effect=raced):renewal.run('sample-one',other['id'],other['version'])
        self.assertEqual(renewal.accounts.get('sample-one',other['id'])['status'],'DISCONNECTED')

    def confirmed_account_after_disconnect(self,identity,version):
        Connections(self.store).disconnect('sample-one',identity,version)
        return self.confirmed()


if __name__=='__main__':unittest.main()
