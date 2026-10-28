"""Shared owner/commit semantics in a synthetic host; not native authentication."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_owner_adapter import OwnerAdapter
from mission_control.operator_identity import Identities
from mission_control.review_access import Access
from mission_control.service import Service
from mission_control.store import Store


class SyntheticNativeIdentities(Identities):
    """Fixture only: real native host must authenticate and bind its own session."""
    def fresh(self, session):
        with self.lock:
            self.prune()
            row = self.sessions.get(session)
            if not row: raise PermissionError('No authenticated native session')
            return self.local(session, row['user']['principal'])


class IOSOwnerConformanceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name)/'owner.sqlite3', seed=False)
        for app in ('owned-app', 'foreign-app'):
            self.store.save_app(app, dict(name='Synthetic app', release='build-1', locale='en-US', currency='USD'))
        self.identities = SyntheticNativeIdentities()
        self.user = dict(principal='native:synthetic-owner', login='synthetic-owner')
        self.identities.sessions['native-session'] = dict(user=self.user, expires=10**12)
        self.service = Service(self.store)
        self.owner = OwnerAdapter(self.service, self.identities)

    def enroll(self):
        return json.loads(self.owner.enroll('native-session', 'owned-app', {'confirm_owner': True}))

    def call(self, operation='growth.history', app='owned-app', body=None, **extra):
        return json.loads(self.owner.call('native-session', json.dumps(dict(
            app_id=app, operation=operation, input=body or {}, **extra)).encode()))

    def listing(self):
        from tests.test_aso_validation import listing
        return dict(id='owner-listing', manifest_version=1, kind='ASO_LISTING',
                    data=dict(release='build-1', listing=listing()))

    def test_explicit_enrollment_and_real_shared_write_read(self):
        self.assertTrue(self.enroll()['configured'])
        self.call('growth.save', body=self.listing())
        self.assertIsInstance(self.call(), dict)
        with self.assertRaises(Invalid): self.enroll()

    def test_unowned_foreign_revoked_and_wrong_role_deny(self):
        with self.assertRaises(PermissionError): self.call()
        self.enroll()
        with self.assertRaises(PermissionError): self.call(app='foreign-app')
        for role, status in [('MAKER', 'ACTIVE'), ('OWNER', 'REVOKED')]:
            with connection(self.store.path) as db:
                db.execute('UPDATE operator_roles SET role=?,status=? WHERE app_id=?',
                           (role, status, 'owned-app'))
            with self.assertRaises(PermissionError): self.call()

    def test_session_expiry_logout_and_body_impersonation_deny(self):
        self.enroll()
        with self.assertRaises(Invalid): self.call(principal='someone-else')
        self.identities.sessions['native-session']['expires'] = 0
        with self.assertRaises(PermissionError): self.call()
        self.assertNotIn('native-session', self.identities.sessions)

    def test_role_revocation_between_admission_and_write_prevents_record(self):
        from mission_control.growth_review_store import GrowthReviews
        self.enroll()
        original = GrowthReviews.save
        def revoke_then_write(instance, app_id, body):
            with connection(self.store.path) as db:
                db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", (app_id,))
            return original(instance, app_id, body)
        with patch.object(GrowthReviews, 'save', revoke_then_write):
            with self.assertRaises(PermissionError): self.call('growth.save', body=self.listing())
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_review_entries').fetchone()[0], 0)

    def test_session_generation_change_during_write_rolls_back(self):
        from mission_control.growth_review_store import GrowthReviews
        self.enroll()
        original = GrowthReviews.commit
        def write_then_replace(instance, *args):
            result = original(instance, *args)
            self.identities.sessions['native-session']['generation'] = 'replacement'
            return result
        with patch.object(GrowthReviews, 'commit', write_then_replace):
            with self.assertRaises(PermissionError): self.call('growth.save', body=self.listing())
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_review_entries').fetchone()[0], 0)

    def test_failed_enrollment_commit_check_leaves_no_owner(self):
        original = Access.write
        def write_then_logout(instance, *args):
            original(instance, *args)
            self.identities.logout('native-session')
        with patch.object(Access, 'write', write_then_logout):
            with self.assertRaises(PermissionError): self.enroll()
        self.assertFalse(Access(self.store).list('owned-app')['configured'])

    def test_editor_route_receives_human_attribution(self):
        from mission_control.video_edit_projects import Projects
        self.enroll()
        actors = []
        def inspect(instance, app_id):
            actors.append(instance.caller())
            return []
        with patch.object(Projects, 'list', inspect): self.assertEqual(self.call('editor.list'), [])
        self.assertEqual(actors, [dict(kind='LOCAL_SESSION')])


if __name__ == '__main__': unittest.main()
