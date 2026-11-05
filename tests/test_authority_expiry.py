"""Synthetic SQLite tests for owner consent and preserved grant lineage."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import tempfile
import threading
import time
import unittest

from mission_control.agent_grants import Grants, current
from mission_control.authority_expiry import AuthorityExpiry
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store


class AuthorityExpiryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'synthetic.sqlite', seed=False)
        self.store.save_app('sample', dict(name='Synthetic', release='v1', locale='en-US', currency='USD'))
        self.owner = dict(principal='owner', login='owner')
        Access(self.store).bootstrap('sample', self.owner, dict(confirm_owner=True))
        self.now = datetime.now(timezone.utc)
        self.grants = Grants(self.store, clock=lambda: self.now)
        self.service = AuthorityExpiry(self.store, clock=lambda: self.now)
        self.body = dict(agent_id='synthetic', manifest_version=1, operations=['growth.read'],
                         expires=(self.now + timedelta(hours=1)).isoformat(), max_calls=3)

    def issue(self):
        return self.grants.issue('sample', self.owner, self.body)

    def review(self, identity):
        return self.service.preview('sample', self.owner, dict(kind='AGENT_GRANT', id=identity,
                                    expires=(self.now + timedelta(days=3)).isoformat()))

    def confirm(self, review, request_id='request-1'):
        return self.service.confirm('sample', self.owner, dict(**review, request_id=request_id,
                                    extended_expiry_consent=True))

    def test_extended_issue_requires_typed_consent_and_persists_proof(self):
        self.body['expires'] = (self.now + timedelta(days=30)).isoformat()
        with self.assertRaises(Invalid): self.issue()
        self.body['extended_expiry_consent'] = 1
        with self.assertRaises(Invalid): self.issue()
        self.body['extended_expiry_consent'] = True
        issued = self.issue()
        status = self.grants.authority_status(issued['grant']['id'], 'sample')
        self.assertEqual(status['consent_revision'], 1)
        self.assertEqual(status['effective_expires'], self.body['expires'])

    def test_extension_preserves_accounting_and_replay_is_idempotent(self):
        issued = self.issue()
        self.grants.admit(issued['token'], dict(app_id='sample', operation='growth.read', input={}))
        with connection(self.store.path) as db:
            before = dict(db.execute('SELECT * FROM agent_grants').fetchone())
        review = self.review(issued['grant']['id'])
        first = self.confirm(review)
        self.assertTrue(self.confirm(review)['replay'])
        self.assertEqual(first['receipt']['new_expiry'], review['preview']['new_expiry'])
        with connection(self.store.path) as db:
            after = dict(db.execute('SELECT * FROM agent_grants').fetchone())
        self.assertEqual(before, after)
        self.assertEqual(self.grants.authority_status(issued['grant']['id'], 'sample')['remaining_calls'], 2)

    def test_consent_and_stale_preview_rejected(self):
        issued = self.issue()
        review = self.review(issued['grant']['id'])
        with self.assertRaises(Invalid):
            self.service.confirm('sample', self.owner, dict(**review, request_id='one', extended_expiry_consent=False))
        self.grants.admit(issued['token'], dict(app_id='sample', operation='growth.read', input={}))
        with self.assertRaises(Invalid): self.confirm(review)
        self.assertEqual(self.service.history('sample', self.owner, 'AGENT_GRANT', issued['grant']['id'])['receipts'], [])

    def test_time_after_lock_and_revocation_cannot_revive(self):
        issued = self.issue()
        review = self.review(issued['grant']['id'])
        self.now += timedelta(hours=1)
        with self.assertRaises(Invalid): self.confirm(review)
        self.now -= timedelta(hours=1)
        self.grants.revoke('sample', self.owner, dict(id=issued['grant']['id'], version=1))
        with self.assertRaises((Invalid, PermissionError)): self.confirm(review)

    def test_new_deadline_does_not_reset_quota_or_old_grant(self):
        issued = self.issue()
        self.confirm(self.review(issued['grant']['id']))
        self.now += timedelta(hours=2)
        with connection(self.store.path) as db:
            row = db.execute('SELECT * FROM agent_grants').fetchone()
            current(db, row, dict(app_id='sample', operation='growth.read'), self.now)
        for _ in range(3):
            self.grants.admit(issued['token'], dict(app_id='sample',operation='growth.read',input={}))
        with self.assertRaises(PermissionError):
            self.grants.admit(issued['token'], dict(app_id='sample',operation='growth.read',input={}))

    def test_writer_wait_rechecks_time_after_lock(self):
        issued = self.issue()
        review = self.review(issued['grant']['id'])
        writer = sqlite3.connect(self.store.path,timeout=5)
        writer.execute('BEGIN IMMEDIATE')
        started = threading.Event()
        def confirm_waiting():
            started.set()
            return self.confirm(review)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(confirm_waiting)
                self.assertTrue(started.wait(2))
                time.sleep(.1)
                self.now += timedelta(hours=1)
                writer.commit()
                with self.assertRaises(Invalid):future.result(timeout=5)
        finally:
            writer.close()
        self.assertEqual(self.service.history('sample',self.owner,'AGENT_GRANT',issued['grant']['id'])['receipts'],[])

    def test_second_extension_and_conflicting_request(self):
        issued = self.issue()
        first = self.review(issued['grant']['id'])
        self.confirm(first)
        second = self.service.preview('sample',self.owner,dict(kind='AGENT_GRANT',id=issued['grant']['id'],
                                      expires=(self.now+timedelta(days=5)).isoformat()))
        with self.assertRaises(Invalid):self.confirm(second,'request-1')
        self.assertEqual(self.confirm(second,'request-2')['receipt']['revision'],2)

    def test_receipts_reject_update_delete_and_replace(self):
        issued = self.issue()
        self.confirm(self.review(issued['grant']['id']))
        with connection(self.store.path) as db:
            receipt = db.execute('SELECT * FROM authority_expiry_consents').fetchone()
            storage_id = db.execute('SELECT rowid FROM authority_expiry_consents').fetchone()[0]
            for statement, values in (
                ('UPDATE authority_expiry_consents SET new_expiry=?', (self.body['expires'],)),
                ('DELETE FROM authority_expiry_consents', ()),
                ('INSERT OR REPLACE INTO authority_expiry_consents VALUES ('+','.join('?' for _ in receipt)+')', tuple(receipt)),
            ):
                with self.assertRaises(sqlite3.IntegrityError):db.execute(statement,values)
            replacement = dict(receipt)
            replacement['authority_id'] = 'different-authority'
            replacement['request_id'] = 'different-request'
            sql='INSERT OR REPLACE INTO authority_expiry_consents (rowid,'+','.join(replacement)+') VALUES ('+','.join('?' for _ in range(len(replacement)+1))+')'
            with self.assertRaises(sqlite3.IntegrityError):db.execute(sql,(storage_id,*replacement.values()))
            self.assertEqual(db.execute('SELECT authority_id FROM authority_expiry_consents').fetchone()[0],issued['grant']['id'])

    def test_membership_revision_change_invalidates_review(self):
        issued = self.issue()
        review = self.review(issued['grant']['id'])
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id='sample' AND principal='owner'")
        with self.assertRaises((Invalid,PermissionError)):self.confirm(review)
        self.assertEqual(self.service.history('sample',self.owner,'AGENT_GRANT',issued['grant']['id'])['receipts'],[])


if __name__ == '__main__':
    unittest.main()
