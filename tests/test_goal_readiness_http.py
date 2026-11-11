"""Exercise goal_readiness through real protected HTTP, never the gateway_token bearer path.

Identity and credentials are synthetic fixtures.
"""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError

from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.review_access import Access
from tests import test_agent_grants as http_fixture
from tests import test_automation_requirements as readiness_fixture
from tests import test_verified_review as identities


class GoalReadinessHTTPTests(unittest.TestCase):
    tearDown = http_fixture.GrantTests.tearDown
    body = readiness_fixture.AutomationReadinessTests.body
    dump = readiness_fixture.AutomationReadinessTests.dump
    profile = readiness_fixture.AutomationReadinessTests.profile
    account = readiness_fixture.AutomationReadinessTests.account

    def setUp(self):
        http_fixture.GrantTests.setUp(self)
        self.observed = datetime.now(timezone.utc)
        self.profile(stamp=self.observed)
        self.account(expires=self.observed.timestamp()+3600)
        with connection(self.store.path) as db:
            data = json.loads(db.execute('SELECT data FROM social_connections').fetchone()[0])
            data['last_read_at'] = self.observed.isoformat()
            db.execute('UPDATE social_connections SET data=?', (json.dumps(data),))
        self.path = '/api/apps/sample-one/agent-grants/automation-readiness'

    def read(self, body=None, client=None, app='sample-one'):
        return (client or self.owner).request('POST', '/api/apps/'+app+'/agent-grants/automation-readiness', self.body() if body is None else body)

    def raw(self, body=None, headers=None, raw=None):
        payload = json.dumps(self.body() if body is None else body).encode() if raw is None else raw
        request = Request(self.origin+self.path, data=payload, method='POST', headers={
            'Origin': self.origin, 'X-CSRF-Token': self.owner.csrf,
            'Content-Type': 'application/json', **(headers or {})})
        try:
            with self.owner.opener.open(request, timeout=10) as result:
                return result.status, json.load(result)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_original_inventory_hash_additive_envelope_and_no_writes_or_secret_access(self):
        before = self.dump()
        with patch('mission_control.agent_access.AgentAccess.secret') as secret, patch('mission_control.agent_native.identity') as tool:
            result = self.read()
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['inventory_sha256'], digest(result['inventory']))
        self.assertEqual(result['inventory']['scope_status'], 'READY_FOR_SCOPE_REVIEW')
        self.assertFalse(result['authority_issued'])
        self.assertFalse(result['inventory']['grants_issued'])
        self.assertEqual(result['inventory']['activation'], 'NOT_PERFORMED')
        self.assertTrue(result['summary']); self.assertTrue(result['next_actions'])
        self.assertEqual(result['artifacts'], [])
        self.assertEqual(before, self.dump())
        secret.assert_not_called(); tool.assert_not_called()
        text = json.dumps(result)
        for private in (readiness_fixture.PRIVATE, 'credential_ref', 'secret_ref', 'executable', 'token_hash'):
            self.assertNotIn(private, text)
        with connection(self.store.path) as db:
            for table in ('agent_grants', 'automation_policies', 'automation_executions', 'jobs'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0], 0)

    def test_facebook_readiness_distinguishes_missing_and_unavailable_credentials(self):
        from uuid import uuid4

        account_ref, config_ref = str(uuid4()), str(uuid4())
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET provider='facebook',secret_ref=?", (account_ref,))
            db.execute("UPDATE social_configs SET provider='facebook',secret_ref=?", (config_ref,))
        selected = self.body(workflows=['social_publish'], social_connection_ids=[readiness_fixture.ACCOUNT])
        before = self.dump()
        for fixture, expected, count in (
            ((None,), 'RECONNECT_REQUIRED', 1),
            (({'value': 'synthetic-user-token'}, None), 'RECONNECT_REQUIRED', 2),
            (Invalid('synthetic private vault error'), 'PROTECTED_STORAGE_UNAVAILABLE', 1),
            (({'value': 'synthetic-user-token'}, {'value': 'synthetic-client-secret'}), None, 2),
        ):
            with self.subTest(expected=expected), patch(
                'mission_control.credential_vault.Vault', autospec=True
            ) as vault:
                fetch = vault.return_value.get
                fetch.side_effect = fixture
                response = self.read(selected)
                self.assertEqual(fetch.call_count, count)
                repairs = {readiness_fixture.ACCOUNT: expected} if expected else {}
                self.assertEqual(response['credential_repairs'], repairs)
                self.assertEqual(response['inventory']['accounts'][0]['status'], 'TESTED_FRESH')
                self.assertEqual(response['inventory_sha256'], digest(response['inventory']))
                self.assertFalse(response['authority_issued'])
                for value in (account_ref, config_ref, 'synthetic-user-token',
                              'synthetic-client-secret', 'synthetic private vault error'):
                    self.assertNotIn(value, json.dumps(response))
        with patch('mission_control.credential_vault.Vault', autospec=True) as vault:
            self.assertEqual(self.read(self.body())['credential_repairs'], {})
            vault.assert_not_called()
        self.assertEqual(before, self.dump())

    def test_organic_channel_readiness_is_owner_only_and_issues_no_authority(self):
        before = self.dump()
        report = self.read(self.body(workflows=['organic_publication'], social_connection_ids=[readiness_fixture.ACCOUNT]))
        inventory = report['inventory']; account = inventory['accounts'][0]
        self.assertTrue(account['publishing_implemented'])
        self.assertEqual(account['publication_connection_provider'], 'tiktok')
        self.assertIn('EXACT_CURRENT_OWNER_PUBLICATION_APPROVAL_REQUIRED', inventory['workflows'][0]['blockers'])
        self.assertIn('Publish an approved post', inventory['workflows'][0]['repair'])
        self.assertFalse(report['authority_issued'])
        self.assertEqual(before, self.dump())
        self.assertNotIn(readiness_fixture.PRIVATE, json.dumps(report))

    def test_gateway_token_cannot_replace_owner_session_and_fresh_identity(self):
        anonymous = OperatorClient(self.origin); anonymous.bootstrap()
        with self.assertRaises(ClientError) as denied:
            self.read(client=anonymous)
        self.assertEqual(denied.exception.status, 403)
        bearer = Request(self.origin+self.path, data=json.dumps(self.body()).encode(), method='POST',
                         headers={'Origin': self.origin, 'X-CSRF-Token': anonymous.csrf,
                                  'Authorization': 'Bearer synthetic-readiness-token', 'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as denied:
            anonymous.opener.open(bearer, timeout=10)
        self.assertEqual(denied.exception.code, 403)
        checker = OperatorClient(self.origin); checker.bootstrap()
        checker.request('POST', '/api/identity/login', {'token': identities.CHECKER_TOKEN})
        Access(self.store).save('sample-one', identities.OWNER, identities.CHECKER,
                               dict(login=identities.CHECKER['login'], role='MAKER', status='ACTIVE', version=None))
        with self.assertRaises(ClientError) as denied:
            self.read(client=checker)
        self.assertEqual(denied.exception.status, 403)
        with patch('mission_control.operator_identity.github_read', side_effect=Invalid('Synthetic identity unavailable')):
            with self.assertRaises(ClientError):
                self.read()
        self.owner.request('POST', '/api/identity/login', {'token': identities.OWNER_TOKEN})
        with self.server.identities.lock:
            for session in self.server.identities.sessions.values():
                session['expires'] = 0
        with self.assertRaises(ClientError) as denied:
            self.read()
        self.assertEqual(denied.exception.status, 403)

    def test_origin_csrf_and_strict_json_boundaries(self):
        before = self.dump()
        # The boundary rejects these requests before reading a body. No unread
        # payload is sent, avoiding the documented Windows TCP reset race.
        for headers in ({'Origin': 'http://foreign.invalid'}, {'X-CSRF-Token': 'wrong'}):
            code, _ = self.raw(headers=headers, raw=b'')
            self.assertEqual(code, 403)
        raw = json.dumps(self.body())[:-1]+',"agent_id":"duplicate"}'
        self.assertEqual(self.raw(raw=raw.encode())[0], 400)
        self.assertEqual(self.raw(body={**self.body(), 'manifest_version': float('nan')})[0], 400)
        self.assertEqual(before, self.dump())

    def test_exact_selection_rejects_authority_fields_duplicates_and_foreign_resources(self):
        self.profile('sample-two', readiness_fixture.FOREIGN, stamp=self.observed)
        self.account('sample-two', readiness_fixture.FOREIGN)
        cases = [dict(self.body(), principal=identities.OWNER['principal']),
                 dict(self.body(), limits={'max_calls': 10}),
                 self.body(workflows=['local_evidence', 'local_evidence']),
                 self.body(workflows=['unknown']),
                 self.body(agent_connection_id=readiness_fixture.FOREIGN),
                 self.body(social_connection_ids=[readiness_fixture.FOREIGN]),
                 self.body(manifest_version=2)]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(ClientError) as denied:
                self.read(body)
            self.assertEqual(denied.exception.status, 400)

    def test_missing_stale_expired_and_parent_workflows_remain_blocked(self):
        missing = self.read(self.body(agent_connection_id=None))
        self.assertEqual(missing['inventory']['inference']['status'], 'MISSING')
        self.assertEqual(missing['status'], 'warning')
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET last_test=?', ((self.observed-timedelta(hours=25)).isoformat(),))
        stale = self.read()
        self.assertEqual(stale['inventory']['inference']['status'], 'STALE')
        expired = self.read(self.body(workflows=['social_publish', 'paid_effects', 'complete_analytics'], social_connection_ids=[readiness_fixture.ACCOUNT]))
        self.assertEqual([w['id'] for w in expired['inventory']['workflows']], ['social_publish', 'paid_effects', 'complete_analytics'])
        self.assertTrue(all(w['blockers'] for w in expired['inventory']['workflows']))
        with connection(self.store.path) as db:
            db.execute('UPDATE social_connections SET expires=?', (self.observed.timestamp()-1,))
        expired = self.read(self.body(social_connection_ids=[readiness_fixture.ACCOUNT]))
        self.assertEqual(expired['inventory']['accounts'][0]['status'], 'EXPIRED')
        # Existing core semantics assess workflow-relevant requirements; merely
        # selecting an unrelated expired account does not widen its authority.
        self.assertFalse(expired['authority_issued'])

    def test_revision_and_manifest_changes_require_current_facts_and_repair_is_read_only(self):
        original = self.read()
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_connections SET version=version+1')
        revised = self.read()
        self.assertNotEqual(original['inventory_sha256'], revised['inventory_sha256'])
        before = self.dump()
        self.assertEqual(revised['inventory'], self.read()['inventory'])
        self.assertEqual(before, self.dump())
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', {**app['data'], 'job': 'Updated synthetic purpose'}, app['version'])
        with self.assertRaises(ClientError):
            self.read()
        self.assertEqual(self.read(self.body(manifest_version=2))['inventory']['app']['version'], 2)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id='sample-one'")
        with self.assertRaises(ClientError) as denied:
            self.read(self.body(manifest_version=2))
        self.assertEqual(denied.exception.status, 403)


if __name__ == '__main__':
    unittest.main()
