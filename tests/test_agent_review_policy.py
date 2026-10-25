"""Actual owner HTTP issuance and ordinary gateway enforcement of review policy."""
from pathlib import Path
import json
import unittest
from mission_control.operator_client import OperatorClient,ClientError
from mission_control.db import connection
from tests import test_agent_grants as fixture
from tests import test_verified_review as identity_fixture


class ReviewPolicyTests(unittest.TestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown
    body=fixture.GrantTests.body
    envelope=fixture.GrantTests.envelope
    listing_body=fixture.GrantTests.listing_body

    def issue_reviewed(self,review_operations=None):
        body=dict(self.body(),review_operations=review_operations if review_operations is not None else ['growth.save'])
        return self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',body)

    def test_policy_is_visible_owner_selected_and_blocks_ordinary_gateway(self):
        issued=self.issue_reviewed();self.assertEqual(issued['grant']['review_operations'],['growth.save'])
        client=OperatorClient(self.origin,grant_token=issued['token'])
        with self.assertRaises(ClientError) as error:client.call(self.envelope('growth.save',self.listing_body()))
        self.assertEqual(error.exception.status,403)
        self.assertEqual(client.call(self.envelope())['history'],[])
        rows=self.grants.list('sample-one',identity_fixture.OWNER)['grants']
        self.assertEqual(rows[0]['review_operations'],['growth.save']);self.assertEqual(rows[0]['used'],1)

    def test_unknown_duplicate_read_or_ungranted_review_policy_is_rejected(self):
        for selected in (['growth.read'],['growth.save','growth.save'],['customer.save'],['human.approve'],'growth.save',[{}]):
            with self.assertRaises(ClientError):self.issue_reviewed(selected)
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0],0)

    def test_legacy_grants_keep_local_behavior_and_exports_have_no_review_policy(self):
        issued=self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',self.body())
        self.assertEqual(issued['grant']['review_operations'],[])
        client=OperatorClient(self.origin,grant_token=issued['token'])
        self.assertIn('hash',client.call(self.envelope('growth.save',self.listing_body())))
        snapshot=json.dumps(self.store.export('sample-one'))
        for name in ('agent_grant_review_policy','agent_review_requests',issued['token']):self.assertNotIn(name,snapshot)
