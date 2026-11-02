"""Synthetic protected schedule authority and no-replay worker tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time
import unittest
from unittest.mock import patch

from mission_control.campaign_schedule import CampaignSchedules, tick
from mission_control.common import Invalid, canonical
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.worker import claim, run_once
from tests.test_campaign_access import CampaignGatewayTests
from tests.test_verified_review import OWNER


class ScheduleTests(unittest.TestCase):
    setUp_base = CampaignGatewayTests.setUp_base
    tearDown = CampaignGatewayTests.tearDown
    body = CampaignGatewayTests.body
    owner_call = CampaignGatewayTests.owner_call
    activate = CampaignGatewayTests.activate

    def setUp(self):
        CampaignGatewayTests.setUp(self)
        from mission_control import campaign_schedule
        original = campaign_schedule.CampaignExecutionService
        wire = patch.object(campaign_schedule, 'CampaignExecutionService',
                            side_effect=lambda store, checker: original(store, checker, self.wire))
        wire.start()
        self.addCleanup(wire.stop)
        network = patch('mission_control.campaign_transport.MetaTransport.request',
                        side_effect=AssertionError('Live provider access is forbidden in this test'))
        network.start()
        self.addCleanup(network.stop)

    @contextmanager
    def owner_bound(self):
        envelope = dict(app_id='sample-one', operation='campaign.schedule.owner', input={})
        session = self.owner.csrf
        with bound_owner(self.store, envelope, self.server.identities, session, OWNER):
            with protected(self.store, envelope):
                yield

    def prepare_batch(self):
        scope = self.activate()
        service = CampaignSchedules(self.store)
        due = datetime.now(timezone.utc) + timedelta(seconds=30)
        with self.owner_bound():
            draft = service.prepare('sample-one', dict(scope_id=scope['scope_id'],
                items=[dict(due_at=due.isoformat(), request=self.post)]))
            active = service.activate('sample-one', draft['summary']['batch_id'], draft['summary_hash'])
        return service, draft, active, due.timestamp()

    def test_due_once_process_special_checked_scope_owner_context_and_verified_receipt(self):
        service, draft, active, due = self.prepare_batch()
        with patch('time.time', return_value=due + 1):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: tick(self.store), range(2)))
            self.assertEqual(sum(results), 1)
            self.assertTrue(run_once(self.store))
            self.assertFalse(run_once(self.store))
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(self.wire.posts, 1)
        self.assertEqual(status['items'][0]['job_status'], 'SUCCEEDED')
        self.assertEqual(status['items'][0]['intent']['status'], 'VERIFIED')
        self.assertNotIn('synthetic-token', canonical(status))

    def test_off_cancels_queued_and_blocks_dispatch(self):
        service, draft, active, due = self.prepare_batch()
        with patch('time.time', return_value=due + 1):
            self.assertEqual(tick(self.store), 1)
            with self.owner_bound():
                result = service.revoke('sample-one', active['id'], active['version'])
            self.assertEqual(result['items'][0]['job_status'], 'CANCELLED')
            self.assertFalse(run_once(self.store))
        self.assertEqual(self.wire.posts, 0)

    def test_expired_running_job_is_never_reclaimed(self):
        service, draft, active, due = self.prepare_batch()
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            self.assertIsNotNone(claim(self.store))
        with patch('time.time', return_value=due + 100):
            self.assertIsNone(claim(self.store))
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(status['items'][0]['job_status'], 'BLOCKED')
        self.assertEqual(self.wire.posts, 0)

    def test_failed_special_lost_response_preserves_unknown_and_does_not_retry(self):
        service, draft, active, due = self.prepare_batch()
        self.wire.fail = True
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            run_once(self.store)
            run_once(self.store)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(self.wire.posts, 1)
        self.assertEqual(status['items'][0]['job_status'], 'BLOCKED')
        self.assertEqual(status['items'][0]['intent']['status'], 'UNKNOWN')

    def test_changed_owner_or_connection_blocks_provider(self):
        service, draft, active, due = self.prepare_batch()
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET version=version+1 WHERE app_id='sample-one'")
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            run_once(self.store)
        self.assertEqual(self.wire.posts, 0)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(status['items'][0]['job_status'], 'BLOCKED')

    def test_changed_owner_or_app_blocks_provider(self):
        for table, update in (
            ('owner', "UPDATE operator_roles SET version=version+1 WHERE app_id='sample-one'"),
            ('app', "UPDATE apps SET version=version+1 WHERE id='sample-one'"),
        ):
            with self.subTest(changed=table):
                service, draft, active, due = self.prepare_batch()
                with connection(self.store.path) as db:
                    db.execute(update)
                with patch('time.time', return_value=due + 1):
                    tick(self.store)
                    run_once(self.store)
                self.assertEqual(self.wire.posts, 0)
                # Restore only synthetic fixture state for the next case.
                with connection(self.store.path) as db:
                    if table == 'owner':
                        db.execute("UPDATE operator_roles SET version=version-1 WHERE app_id='sample-one'")
                    else:
                        db.execute("UPDATE apps SET version=version-1 WHERE id='sample-one'")

    def test_off_during_dispatched_post_keeps_receipt_without_replay(self):
        service, draft, active, due = self.prepare_batch()
        def off_after_send():
            with self.owner_bound():
                service.revoke('sample-one', active['id'], active['version'])
        self.wire.before_return = off_after_send
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            run_once(self.store)
            run_once(self.store)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(self.wire.posts, 1)
        self.assertEqual(status['status'], 'OFF')
        self.assertEqual(status['items'][0]['intent']['status'], 'VERIFYING')

    def test_tampered_due_cannot_accelerate_post(self):
        service, draft, active, due = self.prepare_batch()
        with connection(self.store.path) as db:
            db.execute('UPDATE campaign_schedule_items SET due=0 WHERE batch_id=?', (active['id'],))
        self.assertEqual(tick(self.store), 0)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(status['items'][0]['status'], 'BLOCKED')
        self.assertEqual(self.wire.posts, 0)

    def test_revoked_scope_blocks_new_effects(self):
        service, draft, active, due = self.prepare_batch()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_scopes SET status='REVOKED' WHERE id=?", (draft['summary']['scope_id'],))
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            run_once(self.store)
        self.assertEqual(self.wire.posts, 0)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(status['items'][0]['job_status'], 'BLOCKED')

    def test_exhausted_scope_call_quota_blocks_provider(self):
        service, draft, active, due = self.prepare_batch()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_scopes SET calls=50 WHERE id=?", (draft['summary']['scope_id'],))
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            run_once(self.store)
        self.assertEqual(self.wire.posts, 0)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(status['items'][0]['job_status'], 'BLOCKED')

    def test_provider_boundary_does_not_hold_sqlite_writer_lock(self):
        service, draft, active, due = self.prepare_batch()
        def concurrent_write():
            with connection(self.store.path) as db:
                db.execute("UPDATE apps SET updated=updated WHERE id='sample-one'")
        self.wire.before_return = concurrent_write
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            run_once(self.store)
        with self.owner_bound():
            status = service.status('sample-one', active['id'])
        self.assertEqual(self.wire.posts, 1)
        self.assertEqual(status['items'][0]['intent']['status'], 'VERIFIED')

    def test_tampered_job_payload_is_denied_at_effect_boundary(self):
        service, draft, active, due = self.prepare_batch()
        with patch('time.time', return_value=due + 1):
            tick(self.store)
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET data='{}' WHERE action='campaign_post'")
            run_once(self.store)
        self.assertEqual(self.wire.posts, 0)

    def test_prepare_items_validate_items_need_exact_hash_and_owner_context(self):
        """Exercise owner_context, checked_scope, prepare_items and validate_items through review."""
        scope = self.activate()
        service = CampaignSchedules(self.store)
        due = datetime.now(timezone.utc) + timedelta(seconds=30)
        body = dict(scope_id=scope['scope_id'], items=[dict(due_at=due.isoformat(), request=self.post)])
        with self.assertRaises(PermissionError):
            service.prepare('sample-one', body)
        with self.owner_bound():
            draft = service.prepare('sample-one', body)
            with self.assertRaises(Invalid):
                service.activate('sample-one', draft['summary']['batch_id'], '0' * 64)
            service.activate('sample-one', draft['summary']['batch_id'], draft['summary_hash'])

    def test_existing_special_routes_and_closed_fields(self):
        from mission_control.worker import process_special, failed_special
        from mission_control.campaign_access import validate_fields, scope_owner
        validate_fields('history', {})
        with self.assertRaises(Invalid):
            validate_fields('history', {'owner':'forged'})
        self.assertEqual(scope_owner(self.store, {'principal':'owner'}, 'owner'), 'owner')
        with patch('mission_control.agent_tasks.execute', return_value={'result':'agent'}) as execute:
            self.assertEqual(process_special(self.store, {'action':'agent_run'}, None), {'result':'agent'})
            execute.assert_called_once()
        result, status, delay = failed_special({'action':'drive_import'})
        self.assertEqual((status,delay), ('BLOCKED',0))
        self.assertEqual(result['external_execution'], 'READ_ATTEMPT_MAY_HAVE_OCCURRED')

    def test_persist_job_result_rejects_superseded_job(self):
        from mission_control.worker import persist_job_result
        service, draft, active, due = self.prepare_batch()
        with patch('time.time', return_value=due+1):
            tick(self.store)
            job = claim(self.store)
        with self.owner_bound():
            service.revoke('sample-one', active['id'], active['version'])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=?", (job['id'],))
        persist_job_result(self.store, job, {'result':'late'}, 'SUCCEEDED', 0)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0], 'CANCELLED')

    def test_check_lease_and_check_content_reject_changed_binding(self):
        from mission_control.campaign_schedule_authority import check_lease, check_content
        from mission_control.common import digest
        stamp = datetime.now(timezone.utc)
        body = dict(item_id='item', due_at=stamp.isoformat(), request={'content_hash':'a'*64})
        summary = dict(batch_id='batch', app_id='sample-one', scope_id='scope',
                       scope_hash='approved', owner='owner', items=[body])
        scope = dict(scope_id='scope', approval_hash='approved', owner_principal='owner')
        row = dict(app_id='sample-one', action='campaign_post', batch_id='batch',
                   batch_status='ACTIVE', item_status='QUEUED', job_status='RUNNING',
                   attempts=1, lease=time.time()+60, due=stamp.timestamp(),
                   summary_hash=digest(summary), body_hash=digest(body))
        data = dict(batch_id='batch', item_id='item', scope_id='scope', request=body['request'])
        active = (str(self.store.path.resolve()), 'job', 1)
        check_lease(row, 'sample-one', active)
        check_content(row, data, body, summary, 'sample-one', scope)
        with self.assertRaises(PermissionError):
            check_lease(dict(row, lease=0), 'sample-one', active)
        with self.assertRaises(PermissionError):
            check_content(dict(row, body_hash='wrong'), data, body, summary, 'sample-one', scope)

    def test_history_returns_only_owner_saved_summaries_without_network(self):
        service, draft, active, due = self.prepare_batch()
        with self.owner_bound():
            history = service.history('sample-one')
        self.assertEqual(len(history['batches']), 1)
        self.assertEqual(history['batches'][0]['summary'], draft['summary'])
        self.assertEqual(history['batches'][0]['scope_id'], draft['summary']['scope_id'])
        self.assertNotIn('synthetic-token', canonical(history))
        self.assertEqual(self.wire.posts, 0)

    def test_tick_limits_work_to_twenty_due_items(self):
        scope = self.activate()
        service = CampaignSchedules(self.store)
        due = datetime.now(timezone.utc) + timedelta(seconds=30)
        items = [dict(due_at=due.isoformat(),
                      request=dict(self.post, request_id=f'00000000-0000-4000-8000-{n:012d}'))
                 for n in range(21)]
        with self.owner_bound():
            for batch_items in (items[:20], items[20:]):
                draft = service.prepare('sample-one', dict(scope_id=scope['scope_id'], items=batch_items))
                service.activate('sample-one', draft['summary']['batch_id'], draft['summary_hash'])
        with patch('time.time', return_value=due.timestamp() + 1):
            self.assertEqual(tick(self.store), 20)
            self.assertEqual(tick(self.store), 1)
        self.assertEqual(self.wire.posts, 0)


if __name__ == '__main__':
    unittest.main()
