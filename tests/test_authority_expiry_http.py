"""Actual owner HTTP consent paths; only identity/provider edges are synthetic."""
from datetime import datetime, timedelta, timezone
from http.client import HTTPConnection
import json
import unittest

from mission_control.agent_grants import token_digest
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.review_access import Access
from tests import test_verified_review as identities
from tests import test_agent_grants as grant_fixture
from tests import test_campaign_access as campaign_fixture


class HTTPHelpers:
    def expiry(self, days=3):
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    def route(self, action, app='sample-one'):
        return '/api/apps/' + app + '/authority-expiry/' + action

    def preview(self, kind, identity, days=5):
        return self.owner.request('POST', self.route('preview'),
                                  dict(kind=kind, id=identity, expires=self.expiry(days)))

    def confirm_body(self, review, request_id='extension-one'):
        return dict(review, request_id=request_id, extended_expiry_consent=True)

    def history(self, kind, identity):
        return self.owner.request('POST', self.route('history'), dict(kind=kind, id=identity))

    def wire(self, path, body=None, headers=None, method='POST', authenticated=True):
        """Preserve duplicate headers and JSON bytes instead of normalizing them."""
        raw = body if isinstance(body, bytes) else json.dumps(body or {}).encode()
        values = dict(Host=self.origin[7:], Origin=self.origin,
                      **{'Content-Type': 'application/json', 'Content-Length': str(len(raw))})
        if authenticated:
            values['Cookie'] = '; '.join(cookie.name + '=' + cookie.value for cookie in self.owner.cookies)
            values['X-CSRF-Token'] = self.owner.csrf
        values.update(headers or {})
        http = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            http.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for key, value in values.items():
                for item in value if isinstance(value, list) else [value]:
                    if item is not None:
                        http.putheader(key, item)
            http.endheaders(raw)
            response = http.getresponse()
            return response.status, response.getheaders(), response.read()
        finally:
            http.close()

    def receipt_count(self):
        with connection(self.store.path) as db:
            return db.execute('SELECT count(*) FROM authority_expiry_consents').fetchone()[0]


class AuthorityExpiryHTTPTests(HTTPHelpers, unittest.TestCase):
    setUp = grant_fixture.GrantTests.setUp
    tearDown = grant_fixture.GrantTests.tearDown
    body = grant_fixture.GrantTests.body

    def issue(self, days=None, max_calls=4):
        body = self.body(['operations.read'], max_calls)
        if days is not None:
            body.update(expires=self.expiry(days), extended_expiry_consent=True)
        return self.owner.request('POST', '/api/apps/sample-one/agent-grants/issue', body)

    def grant_row(self, identity):
        with connection(self.store.path) as db:
            return dict(db.execute('SELECT * FROM agent_grants WHERE id=?', (identity,)).fetchone())

    def metadata(self, token):
        return OperatorClient(self.origin, grant_token=token).call(
            dict(app_id='sample-one', operation='operations.read', input={}))

    def test_long_issue_extend_same_credential_and_cumulative_remaining_calls(self):
        issued = self.issue(days=3, max_calls=2)
        identity, token = issued['grant']['id'], issued['token']
        initial = self.metadata(token)['agent_authority']
        self.assertEqual((initial['used'], initial['remaining_calls']), (1, 1))
        self.assertEqual(initial['consent_revision'], 1)
        before = self.grant_row(identity)
        self.assertEqual(before['token_hash'], token_digest(token))
        review = self.preview('AGENT_GRANT', identity)
        self.assertEqual(review['preview']['usage'], dict(used=1, max_calls=2))
        result = self.owner.request('POST', self.route('confirm'), self.confirm_body(review))
        self.assertFalse(result['replay'])
        self.assertEqual(result['receipt']['revision'], 2)
        self.assertEqual(self.grant_row(identity), before, 'extension changed the original grant or accounting')
        final = self.metadata(token)['agent_authority']
        self.assertEqual(final['grant_id'], identity)
        self.assertEqual(final['effective_expires'], review['preview']['new_expiry'])
        self.assertEqual((final['used'], final['max_calls'], final['remaining_calls']), (2, 2, 0))
        with self.assertRaises(ClientError) as denied:
            self.metadata(token)
        self.assertEqual(denied.exception.status, 403)
        history = self.history('AGENT_GRANT', identity)
        self.assertEqual(len(history['receipts']), 2)
        self.assertEqual(history['receipts'][-1], result['receipt'])
        self.assertNotIn(token, json.dumps(history))
        self.assertNotIn('token_hash', json.dumps(history))

    def test_initial_long_deadline_requires_exact_true_consent_over_http(self):
        body = dict(self.body(['operations.read']), expires=self.expiry())
        for flag in (None, False, 1, 'true'):
            with self.subTest(flag=flag):
                proposal = dict(body)
                if flag is not None:
                    proposal['extended_expiry_consent'] = flag
                code, _, _ = self.wire('/api/apps/sample-one/agent-grants/issue', proposal)
                self.assertEqual(code, 400)
        self.assertEqual(self.receipt_count(), 0)
        short = self.issue()
        self.assertEqual(self.history('AGENT_GRANT', short['grant']['id']), {'receipts': []})
        long = self.issue(days=3)
        self.assertEqual(len(self.history('AGENT_GRANT', long['grant']['id'])['receipts']), 1)

    def test_preview_is_readonly_confirm_is_idempotent_and_conflicting_replay_rejects(self):
        issued = self.issue()
        identity = issued['grant']['id']
        before = self.grant_row(identity)
        first = self.preview('AGENT_GRANT', identity)
        self.assertEqual(self.grant_row(identity), before)
        self.assertEqual(self.receipt_count(), 0)
        body = self.confirm_body(first)
        confirmed = self.owner.request('POST', self.route('confirm'), body)
        replay = self.owner.request('POST', self.route('confirm'), body)
        self.assertFalse(confirmed['replay']); self.assertTrue(replay['replay'])
        self.assertEqual(confirmed['receipt'], replay['receipt'])
        self.assertEqual(self.receipt_count(), 1)
        changed = self.preview('AGENT_GRANT', identity, days=6)
        code, _, _ = self.wire(self.route('confirm'), self.confirm_body(changed))
        self.assertEqual(code, 400)
        self.assertEqual(self.receipt_count(), 1)
        self.assertEqual(self.grant_row(identity), before)

    def test_confirmation_rejects_missing_or_forged_consent_and_changed_review(self):
        issued = self.issue(); review = self.preview('AGENT_GRANT', issued['grant']['id'])
        good = self.confirm_body(review)
        for flag in (None, False, 1, 'true'):
            bad = dict(good)
            if flag is None:
                del bad['extended_expiry_consent']
            else:
                bad['extended_expiry_consent'] = flag
            self.assertEqual(self.wire(self.route('confirm'), bad)[0], 400)
        changed = dict(good, preview=dict(review['preview'], new_expiry=self.expiry(9)))
        self.assertEqual(self.wire(self.route('confirm'), changed)[0], 400)
        self.assertEqual(self.wire(self.route('confirm'), dict(good, owner=identities.OWNER['principal']))[0], 400)
        self.assertEqual(self.receipt_count(), 0)
        self.metadata(issued['token'])
        self.assertEqual(self.wire(self.route('confirm'), good)[0], 400, 'stale reviewed usage was accepted')
        self.assertEqual(self.grant_row(issued['grant']['id'])['used'], 1)
        self.assertEqual(self.receipt_count(), 0)

    def test_anonymous_bearer_wrong_role_and_cross_app_cannot_extend(self):
        issued = self.issue(); identity = issued['grant']['id']
        proposal = dict(kind='AGENT_GRANT', id=identity, expires=self.expiry())
        for headers in ({}, {'Authorization': 'Bearer ' + issued['token']}):
            self.assertEqual(self.wire(self.route('preview'), proposal, headers=headers, authenticated=False)[0], 403)
        Access(self.store).save('sample-one', identities.OWNER, identities.CHECKER,
                               dict(login='fixture-checker', role='CHECKER', status='ACTIVE', version=None))
        checker = OperatorClient(self.origin); checker.bootstrap()
        checker.request('POST', '/api/identity/login', dict(token=identities.CHECKER_TOKEN))
        with self.assertRaises(ClientError) as denied:
            checker.request('POST', self.route('preview'), proposal)
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(self.wire(self.route('preview', 'sample-two'), proposal)[0], 403)
        self.owner.request('POST', '/api/apps/sample-two/access/bootstrap', dict(confirm_owner=True,expected_principal=identities.OWNER["principal"],manifest_version=1))
        self.assertEqual(self.wire(self.route('preview', 'sample-two'), proposal)[0], 400)
        self.assertEqual(self.receipt_count(), 0)

    def test_origin_csrf_header_route_and_json_ambiguity_reject_without_receipts(self):
        issued = self.issue(); proposal = dict(kind='AGENT_GRANT', id=issued['grant']['id'], expires=self.expiry())
        for headers in ({'Origin': None}, {'Origin': 'null'}, {'Origin': 'https://evil.example'},
                        {'Origin': [self.origin, self.origin]}, {'Host': [self.origin[7:], self.origin[7:]]},
                        {'X-CSRF-Token': None}, {'X-CSRF-Token': 'wrong'},
                        {'X-CSRF-Token': [self.owner.csrf, self.owner.csrf]}):
            with self.subTest(headers=headers):
                self.assertIn(self.wire(self.route('preview'), proposal, headers=headers)[0], (400, 403))
        for path in (self.route('preview') + '?extra=1', self.route('preview') + '/',
                     self.route('unknown'), self.route('preview').replace('/authority-expiry/', '//authority-expiry/')):
            self.assertIn(self.wire(path, proposal)[0], (400, 403, 404, 405), path)
        self.assertIn(self.wire(self.route('preview'), proposal, method='GET')[0], (400, 403, 404, 405))
        for raw in (b'{"kind":"AGENT_GRANT","kind":"CAMPAIGN"}', b'{"expires":NaN}', b'[]', b'not-json'):
            self.assertEqual(self.wire(self.route('preview'), raw)[0], 400)
        self.assertEqual(self.wire(self.route('history'), dict(kind='AGENT_GRANT', id=issued['grant']['id'], extra=True))[0], 400)
        self.assertEqual(self.receipt_count(), 0)


class CampaignExpiryHTTPTests(HTTPHelpers, unittest.TestCase):
    setUp_base = grant_fixture.GrantTests.setUp
    setUp = campaign_fixture.CampaignGatewayTests.setUp
    tearDown = grant_fixture.GrantTests.tearDown
    body = grant_fixture.GrantTests.body
    owner_call = campaign_fixture.CampaignGatewayTests.owner_call
    activate = campaign_fixture.CampaignGatewayTests.activate

    def test_campaign_extension_preserves_base_limits_and_has_zero_provider_effects(self):
        saved = self.activate(); identity = saved['scope_id']
        with connection(self.store.path) as db:
            before = dict(db.execute('SELECT * FROM campaign_scopes WHERE id=?', (identity,)).fetchone())
            intent_count = db.execute('SELECT count(*) FROM campaign_intents').fetchone()[0]
            paid_count = db.execute('SELECT count(*) FROM campaign_paid_intents').fetchone()[0]
        review = self.preview('CAMPAIGN', identity)
        self.assertEqual(review['preview']['usage']['calls'], before['calls'])
        self.assertEqual(review['preview']['usage']['max_total_minor'], 0)
        result = self.owner.request('POST', self.route('confirm'), self.confirm_body(review, 'campaign-extension'))
        self.assertEqual(result['receipt']['authority_id'], identity)
        with connection(self.store.path) as db:
            after = dict(db.execute('SELECT * FROM campaign_scopes WHERE id=?', (identity,)).fetchone())
            self.assertEqual(db.execute('SELECT count(*) FROM campaign_intents').fetchone()[0], intent_count)
            self.assertEqual(db.execute('SELECT count(*) FROM campaign_paid_intents').fetchone()[0], paid_count)
        self.assertEqual(after, before)
        self.assertEqual(self.wire.posts, 0)
        status = self.owner_call('status', {'scope_id': identity})
        self.assertEqual(status['scope']['permission_expires_at'], review['preview']['new_expiry'])

    def test_campaign_initial_long_date_requires_owner_consent_without_sending(self):
        self.scope['expires_at'] = self.expiry()
        with self.assertRaises(ClientError) as denied:
            self.owner_call('prepare', {'scope': self.scope})
        self.assertEqual(denied.exception.status, 400)
        self.scope['extended_expiry_consent'] = True
        saved = self.activate()
        history = self.history('CAMPAIGN', saved['scope_id'])
        self.assertEqual(len(history['receipts']), 1)
        self.assertEqual(self.wire.posts, 0)


if __name__ == '__main__':
    unittest.main()
