"""Actual isolated SQLite ledger state, privacy and agent approval invalidation."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.agent_economics import derive
from mission_control.agent_context import snapshot
from mission_control.agent_tasks import proposal
from mission_control.common import Invalid,canonical
from mission_control.ledger import Ledger
from mission_control.store import Store
from mission_control.worker import run_once
from tests.test_ledger import cohort,event
from tests import test_ledger as ledger_fixtures
from tests import test_agent_tasks as tasks
from tests.test_agent_access import answer


def seed(store):
    app=store.app('sample-one')
    store.save_app('sample-one',{**app['data'],'release':'build-1','locale':'en-US'},app['version'])
    ledger=Ledger(store.path)
    ledger.define('sample-one',cohort(source='CONFIDENTIAL_COHORT_SOURCE_5811'))
    return ledger


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'ledger.sqlite3')

    def test_derive_missing_inconclusive_and_reconciled_using_real_ledger(self):
        self.assertEqual(derive(self.store,self.store.app('sample-one'))[1]['state'],'UNAVAILABLE')
        ledger=seed(self.store)
        self.assertEqual(derive(self.store,self.store.app('sample-one'))[1]['state'],'INCONCLUSIVE')
        ledger.ingest('sample-one',dict(cohort_id='pilot-1',events=ledger_fixtures.LedgerTests.base(None)))
        reports,summary=derive(self.store,self.store.app('sample-one'))
        self.assertEqual(reports[0]['net_proceeds_minor'],2000)
        self.assertEqual(summary['state'],'SUPPLIED_RECONCILED')
        self.assertNotIn('net_proceeds_minor',canonical(summary))
        self.assertNotIn('opaque-1',canonical(summary))
        self.assertNotIn('CONFIDENTIAL',canonical(snapshot(self.store,'sample-one')))

    def test_snapshot_ledger_stage_uses_latest_inconclusive_window(self):
        seed(self.store)
        app=self.store.app('sample-one')
        self.store.save_record('sample-one',dict(kind='cohort',title='Operator assertion',source='Synthetic',data=dict(mature=True)))
        value=snapshot(self.store,'sample-one')
        stage=next(s for s in value['sources'] if s['id']=='stage_4')
        self.assertEqual(stage['data']['status'],'BLOCKED')
        self.assertGreaterEqual(stage['data']['missing_count'],2)
        self.assertEqual(next(s for s in value['sources'] if s['id']=='ledger_state')['data']['state'],'INCONCLUSIVE')

    def test_late_adjustment_changes_hash_even_if_reconciled_status_remains(self):
        ledger=seed(self.store);ledger.ingest('sample-one',dict(cohort_id='pilot-1',events=ledger_fixtures.LedgerTests.base(None)))
        before=derive(self.store,self.store.app('sample-one'))[1]
        ledger.ingest('sample-one',dict(cohort_id='pilot-1',events=[event('refund','REFUND',day='2026-10-10',amount=200,related='purchase')]))
        after=derive(self.store,self.store.app('sample-one'))[1]
        self.assertNotEqual(before['source_sha256'],after['source_sha256'])
        self.assertEqual(before['state'],after['state'])
        self.assertNotIn('refunds_minor',canonical(after))

    def test_index_overflow_fails_before_loading_event_contents(self):
        seed(self.store)
        with patch('mission_control.agent_economics.LIMIT',0),patch.object(Ledger,'reports') as read,self.assertRaisesRegex(Invalid,'narrow or archive'):
            derive(self.store,self.store.app('sample-one'))
        read.assert_not_called()

    def test_other_app_ledger_does_not_change_selected_context(self):
        before=snapshot(self.store,'sample-one')
        Ledger(self.store.path).define('sample-two',cohort())
        self.assertEqual(before,snapshot(self.store,'sample-one'))


class EconomicsApprovalTests(unittest.TestCase):
    setUp=tasks.AgentTaskTests.setUp
    approve=tasks.AgentTaskTests.approve
    result=tasks.AgentTaskTests.result

    def ready(self):
        from mission_control.db import connection
        self.ledger=seed(self.store)
        with connection(self.store.path) as db:db.execute("UPDATE agent_connections SET status='TESTED' WHERE id=?",(self.identity,))
        self.access.routes('sample-one',dict(version=0,mode='byok',routes={'campaign_plan':self.identity}))

    def change(self):
        self.ledger.ingest('sample-one',dict(cohort_id='pilot-1',events=[event('install','INSTALL')]))

    def test_guard_rejects_changed_ledger_before_inference(self):
        self.ready();self.approve('campaign_plan');self.change()
        with patch('mission_control.agent_tasks.api_run') as call:
            run_once(self.store);call.assert_not_called()
        self.assertEqual(self.result()['status'],'BLOCKED')

    def test_live_guard_rejects_changed_ledger_during_inference(self):
        self.ready();self.approve('campaign_plan')
        def provider(*args):self.change();return answer(),{}
        with patch('mission_control.agent_tasks.api_run',side_effect=provider):run_once(self.store)
        self.assertEqual(self.result()['status'],'BLOCKED')


if __name__=='__main__':unittest.main()
