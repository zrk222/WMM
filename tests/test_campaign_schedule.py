"""Synthetic protected schedule authority and no-replay worker tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time
import unittest
from unittest.mock import patch

from mission_control.campaign_schedule import CampaignSchedules, tick
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.store import Store
from mission_control.worker import claim, run_once
from tests.test_campaign_access import CampaignGatewayTests
from tests.test_campaign_execution import FakePaidTransport
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
        self.real_service_class = original
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

    def test_corrupt_due_batch_is_isolated_and_other_batch_executes_once(self):
        _, _, damaged, first_due = self.prepare_batch()
        service, _, valid, second_due = self.prepare_batch()
        private_payload = '{synthetic-private-input'
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_schedule_batches SET summary=? WHERE id=?",
                       (private_payload, damaged['id']))
        with patch('time.time', return_value=max(first_due, second_due) + 1):
            self.assertEqual(tick(self.store), 1)
            reopened = Store(self.store.path)
            self.assertEqual(tick(reopened), 0)
            self.assertTrue(run_once(reopened))
            self.assertFalse(run_once(reopened))
        with connection(self.store.path) as db:
            blocked = db.execute("SELECT status,job_id FROM campaign_schedule_items WHERE batch_id=?",
                                 (damaged['id'],)).fetchone()
            self.assertEqual((blocked['status'], blocked['job_id']), ('BLOCKED', None))
            summary = db.execute("SELECT summary FROM campaign_schedule_batches WHERE id=?",
                                 (damaged['id'],)).fetchone()[0]
            self.assertEqual(summary, private_payload)
            audits = db.execute("SELECT detail FROM audit WHERE action='campaign_schedule.blocked'").fetchall()
            self.assertEqual(len(audits), 1)
            self.assertIn('SAVED_ITEM_INTEGRITY', audits[0]['detail'])
            self.assertNotIn(private_payload, audits[0]['detail'])
        with self.owner_bound():
            status = service.status('sample-one', valid['id'])
        self.assertEqual(self.wire.posts, 1)
        self.assertEqual(status['items'][0]['intent']['status'], 'VERIFIED')

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
        stamp = datetime.fromtimestamp(time.time()-1, timezone.utc)
        body = dict(item_id='item', due_at=stamp.isoformat(), request={'content_hash':'a'*64})
        summary = dict(batch_id='batch', app_id='sample-one', scope_id='scope',
                       scope_hash='approved', owner='owner', items=[body])
        scope = dict(scope_id='scope', approval_hash='approved', owner_principal='owner',
                     expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
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

    def paid_fixture(self):
        organic = self.activate()
        self.owner_call('publish', {'scope_id': organic['scope_id'], 'request': self.post})
        self.wire = FakePaidTransport()
        creds = patch.object(self.real_service_class, '_credentials',
                      return_value=({}, 'synthetic-secret', {'access_token':'synthetic-token','page_token':'synthetic-token'}))
        creds.start()
        self.addCleanup(creds.stop)
        target = {'countries':['CA']}
        self.scope.update(ad_account_id='456', max_campaigns=2, max_campaign_minor=100, max_total_minor=100,
                          approved_targeting_hashes=[digest(target)], billing_acknowledged=True,
                          ordinary_ad_attestation=True)
        scope = self.activate()
        due = datetime.now(timezone.utc) + timedelta(seconds=30)
        request = dict(request_id='33333333-3333-4333-8333-333333333333', post_id='123_777',
            content_hash=self.content, rights_hash='b'*64, targeting_hash=digest(target), targeting=target,
            lifetime_budget_minor=80, end_time=(due+timedelta(minutes=30)).isoformat(), name='Synthetic promotion')
        return scope, due, request

    def paid_batch(self, scope, due, requests):
        service = CampaignSchedules(self.store)
        items = [dict(due_at=due.isoformat(), operation='campaign.ad-launch', request=request) for request in requests]
        with self.owner_bound():
            draft = service.prepare('sample-one', dict(scope_id=scope['scope_id'], items=items))
            active = service.activate('sample-one', draft['summary']['batch_id'], draft['summary_hash'])
        return service, active

    def test_paid_schedule_verified_promotion_and_retained_commitment(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            run_once(self.store)
            run_once(self.store)
        with self.owner_bound():
            item = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(item['effective_status'], 'ACTIVE_VERIFIED')
        self.assertEqual(item['intent']['commitment'], 80)
        self.assertEqual(len(self.wire.objects), 4)

    def test_paid_unknown_response_retains_commitment_and_never_replays(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        self.wire.fail_kind = 'adset'
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            run_once(self.store)
            run_once(self.store)
        with self.owner_bound():
            item = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(item['intent']['status'], 'UNKNOWN')
        self.assertEqual(item['intent']['commitment'], 80)
        self.assertEqual(item['effective_status'], 'NEEDS_RECONCILIATION')
        self.assertEqual(item['job_status'], 'BLOCKED')

    def test_paid_review_rejects_unverified_post_and_outside_targeting(self):
        scope, due, request = self.paid_fixture()
        service = CampaignSchedules(self.store)
        for bad in (dict(request, post_id='123_999'), dict(request, targeting_hash='a'*64)):
            with self.owner_bound():
                with self.assertRaises((Invalid, PermissionError)):
                    service.prepare('sample-one', dict(scope_id=scope['scope_id'],
                        items=[dict(due_at=due.isoformat(), operation='campaign.ad-launch', request=bad)]))
        self.assertEqual(len(self.wire.objects), 0)

    def test_paid_due_jobs_preserve_account_wide_commitment_limit(self):
        scope, due, request = self.paid_fixture()
        other = dict(request, request_id='44444444-4444-4444-8444-444444444444')
        service, active = self.paid_batch(scope, due, [request, other])
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sum(pool.map(lambda _: run_once(self.store), range(2))), 2)
        with self.owner_bound():
            items = service.status('sample-one', active['id'])['items']
        self.assertCountEqual([item['job_status'] for item in items], ['SUCCEEDED','BLOCKED'])
        self.assertEqual(sum(item['intent']['commitment'] for item in items if item['intent']), 80)
        self.assertEqual(len(self.wire.objects), 4)

    def test_paid_job_lease_expiry_does_not_dispatch(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            self.assertIsNotNone(claim(self.store))
        with patch('time.time', return_value=due.timestamp()+100):
            self.assertIsNone(claim(self.store))
        with self.owner_bound():
            item = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(item['job_status'], 'BLOCKED')
        self.assertEqual(len(self.wire.objects), 0)

    def test_paid_operation_tampering_is_blocked_before_provider(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET data=replace(data,'campaign.ad-launch','campaign.publish') WHERE action='campaign_ad'")
            run_once(self.store)
        with self.owner_bound():
            item = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(item['job_status'], 'BLOCKED')
        self.assertEqual(len(self.wire.objects), 0)

    def test_paid_worker_argument_substitution_is_blocked(self):
        from mission_control.worker import process
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            job = claim(self.store)
            altered = dict(job, data=dict(job['data'], request=dict(request, name='Unapproved name')))
            with self.assertRaises(PermissionError):
                process(self.store, altered)
        self.assertEqual(len(self.wire.objects), 0)

    def test_paid_off_during_mutation_retains_receipt_and_commitment(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        create = self.wire.create_paid
        def create_then_off(kind, account, fields, token, secret, alive):
            result = create(kind, account, fields, token, secret, alive)
            if kind == 'campaign':
                with self.owner_bound():
                    service.revoke('sample-one', active['id'], active['version'])
            return result
        self.wire.create_paid = create_then_off
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            run_once(self.store)
            run_once(self.store)
        with self.owner_bound():
            item = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(item['job_status'], 'BLOCKED')
        self.assertEqual(item['intent']['commitment'], 80)
        self.assertEqual(item['effective_status'], 'NEEDS_RECONCILIATION')
        self.assertEqual(len(self.wire.objects), 1)

    def test_paid_scope_revocation_retains_separate_owner_pause(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            run_once(self.store)
        result = self.owner_call('revoke', {'scope_id': scope['scope_id']})
        self.assertEqual(result['pause_results'][0]['status'], 'PAUSED_campaign')
        with self.owner_bound():
            stopped = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(stopped['effective_status'], 'PAUSED_VERIFIED')
        self.assertEqual(stopped['intent']['commitment'], 80)

    def test_paid_crash_pending_step_requires_reconciliation_no_replay(self):
        scope, due, request = self.paid_fixture()
        service, active = self.paid_batch(scope, due, [request])
        create = self.wire.create_paid
        def crash(kind, account, fields, token, secret, alive):
            if kind == 'adset':
                alive()
                raise KeyboardInterrupt('synthetic abrupt worker loss')
            return create(kind, account, fields, token, secret, alive)
        self.wire.create_paid = crash
        with patch('time.time', return_value=due.timestamp()+1):
            tick(self.store)
            with self.assertRaises(KeyboardInterrupt):
                run_once(self.store)
        with patch('time.time', return_value=due.timestamp()+100):
            self.assertIsNone(claim(self.store))
        with self.owner_bound():
            item = service.status('sample-one', active['id'])['items'][0]
        self.assertEqual(item['job_status'], 'BLOCKED')
        self.assertEqual(item['intent']['status'], 'PENDING_CREATE_adset')
        self.assertEqual(item['intent']['commitment'], 80)
        self.assertEqual(item['effective_status'], 'NEEDS_RECONCILIATION')
        self.assertEqual(len(self.wire.objects), 1)
        observed = self.owner_call('reconcile', {'scope_id':scope['scope_id'], 'intent_id':item['intent']['id']})
        self.assertEqual(observed['status'], 'UNKNOWN')
        self.assertEqual(observed['commitment'], 80)

    def test_paid_review_rejects_end_outside_scope_and_before_due(self):
        scope, due, request = self.paid_fixture()
        service = CampaignSchedules(self.store)
        for end in (due-timedelta(seconds=1), due+timedelta(hours=2)):
            item = dict(due_at=due.isoformat(), operation='campaign.ad-launch',
                        request=dict(request, end_time=end.isoformat()))
            with self.owner_bound():
                with self.assertRaises((Invalid, PermissionError)):
                    service.prepare('sample-one', dict(scope_id=scope['scope_id'], items=[item]))
        self.assertEqual(len(self.wire.objects), 0)


if __name__ == '__main__':
    unittest.main()
