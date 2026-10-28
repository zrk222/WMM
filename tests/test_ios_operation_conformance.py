"""Real shared-domain admissions over the in-process transport; no device claim."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import tempfile
import unittest
from unittest.mock import patch

from mission_control.agent_grants import Grants
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_operation_adapter import ScopedAgentAdapter
from mission_control.review_access import Access
from mission_control.service import Service
from mission_control.store import Store


class IOSOperationConformanceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / 'ios.sqlite', seed=False)
        for app in ('first-app', 'foreign-app'):
            self.store.save_app(app, {'name': 'Synthetic native test', 'release': 'build-1', 'locale': 'en-US', 'currency': 'USD'})
        self.user = {'principal': 'synthetic-native-owner', 'login': 'synthetic-owner'}
        Access(self.store).bootstrap('first-app', self.user, {'confirm_owner': True})
        self.now = datetime.now(timezone.utc)
        self.grants = Grants(self.store, lambda: self.now)
        self.service = Service(self.store)
        self.adapter = ScopedAgentAdapter(self.service, lambda: self.now)

    def issue(self, max_calls=10, operations=None, review=None):
        body = dict(agent_id='native-agent', manifest_version=1,
                    operations=operations or ['growth.history'], max_calls=max_calls,
                    expires=(self.now + timedelta(hours=1)).isoformat())
        if review is not None:
            body['review_operations'] = review
        return self.grants.issue('first-app', self.user, body)

    def call(self, token, operation='growth.history', app='first-app', data=None):
        return json.loads(self.adapter.call(token, json.dumps(dict(
            app_id=app, operation=operation, input=data or {})).encode()))

    def test_real_read_and_quota_denial(self):
        issued = self.issue(max_calls=1)
        self.assertIsInstance(self.call(issued['token']), dict)
        with self.assertRaises(PermissionError):
            self.call(issued['token'])

    def test_foreign_operation_revoked_expired_and_changed_scope_deny(self):
        issued = self.issue()
        with self.assertRaises(PermissionError):
            self.call(issued['token'], app='foreign-app')
        with self.assertRaises(PermissionError):
            self.call(issued['token'], operation='measurement.read')
        self.now += timedelta(hours=2)
        with self.assertRaises(PermissionError):
            self.call(issued['token'])
        self.now -= timedelta(hours=2)
        self.grants.revoke('first-app', self.user, dict(id=issued['grant']['id'], version=1))
        with self.assertRaises(PermissionError):
            self.call(issued['token'])
        fresh = self.issue()
        with connection(self.store.path) as db:
            db.execute("UPDATE apps SET version=version+1 WHERE id='first-app'")
        with self.assertRaises(PermissionError):
            self.call(fresh['token'])

    def test_invalid_payload_does_not_consume_a_call(self):
        issued = self.issue(max_calls=1)
        with self.assertRaises(Invalid):
            self.adapter.call(issued['token'], b'{"operation":"shell"}')
        self.call(issued['token'])

    def test_reviewed_write_cannot_bypass_checkpoint(self):
        issued = self.issue(operations=['growth.save'], review=['growth.save'])
        data = dict(id='example', manifest_version=1, kind='ASO_LISTING', data={})
        with self.assertRaises((PermissionError, Invalid)):
            self.call(issued['token'], operation='growth.save', data=data)
        self.assertEqual(self.grants.list('first-app', self.user)['grants'][0]['used'], 0)

    def test_shared_write_and_revocation_at_commit(self):
        from tests.test_aso_validation import listing
        from mission_control.growth_review_store import GrowthReviews
        issued = self.issue(operations=['growth.save', 'growth.history'])
        data = dict(id='native-listing', manifest_version=1, kind='ASO_LISTING',
                    data=dict(release='build-1', listing=listing()))
        self.call(issued['token'], operation='growth.save', data=data)
        self.assertIsInstance(self.call(issued['token']), dict)
        original = GrowthReviews.save
        def revoke_then_save(reviews, app_id, body):
            self.grants.revoke('first-app', self.user, dict(id=issued['grant']['id'], version=1))
            return original(reviews, app_id, body)
        data['id'] = 'must-not-commit'
        with patch.object(GrowthReviews, 'save', revoke_then_save):
            with self.assertRaises(PermissionError):
                self.call(issued['token'], operation='growth.save', data=data)


if __name__ == '__main__':
    unittest.main()
