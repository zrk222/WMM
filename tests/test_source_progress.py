"""Source handoff truth, bounded invalid indexes, and restart readback."""
import unittest
from unittest.mock import patch
from mission_control.common import canonical, now
from mission_control.db import connection
from mission_control.store import Store
from mission_control.resolutions import Resolutions
from mission_control.agent_feedback import feedback, child_state, child_fingerprint
from mission_control.source_progress import valid_children, state
from mission_control.source_progress import children as source_children
from mission_control.worker import run_once
from tests import test_resolutions as fixtures


class SourceProgressTests(unittest.TestCase):
    setUp = fixtures.ResolutionPlanTests.setUp
    request = fixtures.ResolutionExecutionTests.request

    def dispatch(self):
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', {**app['data'], 'store_app_id': '123'}, app['version'])
        self.store.save_record('sample-one', dict(kind='connection', title='Synthetic source', source='Fixture',
            data=dict(provider='app_store', store_app_id='123', account_id='0', env_ref='SYNTHETIC_TOKEN')))
        job = Resolutions(self.store).start('sample-one', self.request('collect_sources'))
        self.assertTrue(run_once(self.store))
        row = Resolutions(self.store).history('sample-one')[0]
        return job, [r['job_id'] for r in row['children']]

    def projected(self, store=None):
        store = store or self.store
        row = Resolutions(store).history('sample-one')[0]
        agent = feedback(store, store.app('sample-one'))['latest'][0]
        self.assertEqual(row['status'], agent['state'])
        self.assertFalse(row['automatically_verified'])
        return row

    def test_real_worker_progress_and_restart_have_current_summaries(self):
        _, children = self.dispatch()
        row = self.projected()
        self.assertEqual(row['status'], 'COLLECTING_SOURCES')
        self.assertIn('0 of 3', row['summary'])
        with patch('mission_control.worker.sync', return_value={'fixture': True}) as identity, \
             patch('mission_control.worker.read_report', return_value={'fixture': True}) as report:
            self.assertTrue(run_once(self.store))
            self.assertIn('1 of 3', self.projected()['summary'])
            for _ in range(2): self.assertTrue(run_once(self.store))
            self.assertEqual(identity.call_count + report.call_count, 3)
        with patch('mission_control.worker.sync', side_effect=AssertionError('Readback must not request providers')):
            row = self.projected(Store(self.store.path))
        self.assertEqual(row['status'], 'EVIDENCE_GATHERED')
        self.assertIn('All 3', row['summary'])
        self.assertIn('unverified', row['summary'])
        self.assertIn('Review the collected reports', row['next_actions'][0])
        self.assertEqual(row['proof_status'], 'PARTIAL')
        self.assertEqual([r['job_id'] for r in row['children']], children)

    def test_terminal_failures_keep_completed_reports_and_offer_repair(self):
        _, ids = self.dispatch()
        for failure in ('BLOCKED', 'FAILED', 'CANCELLED'):
            with self.subTest(failure=failure), connection(self.store.path) as db:
                db.execute("UPDATE jobs SET status='SUCCEEDED',result='{}' WHERE id=?", (ids[0],))
                db.execute('UPDATE jobs SET status=? WHERE id=?', (failure, ids[1]))
            row = self.projected()
            self.assertEqual(row['status'], 'NEEDS_RESOLUTION')
            self.assertIn('retained', row['summary'])
            self.assertIn('approve a current collection proposal', row['next_actions'][0])
            self.assertEqual(row['children'][0]['status'], 'SUCCEEDED')

    def test_invalid_duplicate_and_oversized_indexes_never_lookup(self):
        bad = [None, {}, [], [''], ['x', 'x'], ['x' * 121], [{}], list(map(str, range(13)))]
        for identities in bad:
            with self.subTest(identities=identities), patch('mission_control.source_progress.connection') as opened:
                self.assertFalse(valid_children(identities))
                # Validation must precede opening a DB for malformed references.
                self.assertEqual(child_state(self.store, 'sample-one', identities), 'NEEDS_RESOLUTION')
                opened.assert_not_called()

    def test_unknown_child_status_cannot_become_collecting_forever(self):
        _, ids = self.dispatch()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='UNRECOGNIZED' WHERE id=?", (ids[0],))
        self.assertEqual(self.projected()['status'], 'NEEDS_RESOLUTION')
        self.assertEqual(state(['SUCCEEDED', 'UNRECOGNIZED']), 'NEEDS_RESOLUTION')

    def test_maximum_collection_uses_twelve_local_lookups_and_invalid_index_uses_none(self):
        from unittest.mock import MagicMock
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = dict(action='sync', status='SUCCEEDED')
        rows = source_children(db, 'sample-one', list(map(str, range(12))))
        self.assertEqual(db.execute.call_count, 12)
        self.assertEqual(state([r['status'] for r in rows]), 'EVIDENCE_GATHERED')
        db.reset_mock()
        self.assertEqual(source_children(db, 'sample-one', ['duplicate', 'duplicate'])[0]['status'], 'INVALID_CHILD_INDEX')
        db.execute.assert_not_called()

    def test_falsey_malformed_child_fingerprints_are_not_empty_success(self):
        for identities in (None, {}, '', 0):
            with self.subTest(identities=identities):
                parent = dict(app_id='sample-one', result=dict(children=identities))
                self.assertEqual(child_fingerprint(self.store, parent), 'INVALID_CHILD_INDEX')

    def test_successful_foreign_or_nonread_job_cannot_satisfy_collection(self):
        _, ids = self.dispatch()
        for change in ("app_id='sample-two'", "action='pipeline'"):
            with self.subTest(change=change), connection(self.store.path) as db:
                db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id IN (?,?,?)", ids)
                db.execute('UPDATE jobs SET ' + change + ' WHERE id=?', (ids[0],))
            self.assertEqual(self.projected()['status'], 'NEEDS_RESOLUTION')
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET app_id='sample-one',action='sync' WHERE id=?", (ids[0],))

    def test_duplicate_persisted_index_and_fingerprint_fail_closed(self):
        parent, ids = self.dispatch()
        value = dict(status='WAITING_FOR_SOURCES', children=[ids[0], ids[0]], summary='Untrusted text')
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (ids[0],))
            db.execute('UPDATE jobs SET result=? WHERE id=?', (canonical(value), parent['id']))
        self.assertEqual(self.projected()['status'], 'NEEDS_RESOLUTION')
        self.assertEqual(child_fingerprint(self.store, dict(app_id='sample-one', result=value)), 'INVALID_CHILD_INDEX')

    def test_completed_dispatch_is_not_claimed_as_verified_campaign(self):
        _, ids = self.dispatch()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED',result='{}',updated=? WHERE id IN (?,?,?)", [now(), *ids])
        row = self.projected()
        self.assertEqual(row['job_status'], 'SUCCEEDED')
        self.assertEqual(row['status'], 'EVIDENCE_GATHERED')
        self.assertNotIn('dispatched', row['summary'])
        self.assertEqual(row['proof_status'], 'PARTIAL')


if __name__ == '__main__': unittest.main()
