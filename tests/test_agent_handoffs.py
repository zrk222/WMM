"""Isolated handoff tests exercise the real owner and bearer operation transports."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.worker import enqueue
from mission_control.agent_handoffs import report_summary
from tests import test_agent_grants as fixture


class HandoffTests(unittest.TestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown
    body=fixture.GrantTests.body
    issue=fixture.GrantTests.issue
    envelope=fixture.GrantTests.envelope

    def grant(self, agent, operations):
        return self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',
            dict(self.body(operations),agent_id=agent))

    def create(self,job,recipient='replacement',operations=None):
        return self.owner.request('POST','/api/apps/sample-one/agent-grants/handoff-create',
            dict(job_id=job['id'],recipient=recipient,operations=operations or ['jobs.read'],
                 expires=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()))

    def resume(self,client,handoff,app='sample-one'):
        return client.call(dict(app_id=app,operation='handoff.resume',resource_id=handoff['id'],
                                input=dict(version=handoff['version'],payload_hash=handoff['payload_hash'])))

    def test_owner_handoff_resumes_original_without_exposing_key_or_new_job(self):
        secret='synthetic-private-request-key'
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=2),secret)
        saved=self.create(job);grant=self.grant('replacement',['handoff.resume','jobs.read'])
        client=OperatorClient(self.origin,grant_token=grant['token'])
        first=self.resume(client,saved);again=self.resume(client,saved)
        self.assertEqual(first['resume'],'RESUME_ADMITTED')
        self.assertEqual(first['job_id'],job['id']);self.assertEqual(first['id'],again['id'])
        self.assertNotIn(secret,json.dumps(first));self.assertNotIn(grant['token'],json.dumps(first))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
            self.assertNotIn(secret,db.execute('SELECT payload FROM agent_handoffs').fetchone()[0])

    def test_owner_catalog_route_is_authorized_and_cannot_impersonate_recipient(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=1),'private-key')
        body=dict(job_id=job['id'],recipient='replacement',operations=['jobs.read'],
                  expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat())
        saved=self.owner.call(self.envelope('handoff.create',body))
        self.assertEqual(saved['job_id'],job['id'])
        with self.assertRaises(ClientError):self.owner.call(dict(app_id='sample-one',operation='handoff.resume',resource_id=saved['id'],
            input=dict(version=saved['version'],payload_hash=saved['payload_hash'])))

    def test_recipient_cross_app_revocation_and_stale_context_fail(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=1),'old-private-key')
        saved=self.create(job);wrong=self.grant('wrong-agent',['handoff.resume','jobs.read'])
        client=OperatorClient(self.origin,grant_token=wrong['token'])
        with self.assertRaises(ClientError):self.resume(client,saved)
        with self.assertRaises(ClientError):self.resume(client,saved,'sample-two')
        right=self.grant('replacement',['handoff.resume','jobs.read'])
        good=OperatorClient(self.origin,grant_token=right['token'])
        with connection(self.store.path) as db:db.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(dict(stage=3)),job['id']))
        with self.assertRaises(ClientError):self.resume(good,saved)
        fresh=self.create(job)
        self.owner.request('POST','/api/apps/sample-one/agent-grants/handoff-revoke',dict(id=fresh['id'],version=fresh['version']))
        with self.assertRaises(ClientError):self.resume(good,fresh)

    def test_agent_source_revocation_and_concurrent_claims(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=4),'request-four')
        source=self.grant('source',['handoff.create','jobs.read'])
        source_client=OperatorClient(self.origin,grant_token=source['token'])
        value=dict(job_id=job['id'],recipient='replacement',operations=['jobs.read'],
                   expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat())
        handoff=source_client.call(self.envelope('handoff.create',value))
        target=self.grant('replacement',['handoff.resume','jobs.read'])
        def claim(_):
            try:return self.resume(OperatorClient(self.origin,grant_token=target['token']),handoff)['resume']
            except ClientError:return 'DENIED'
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(claim,range(4)))
        self.assertEqual(results.count('RESUME_ADMITTED'),4)
        self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',dict(id=source['grant']['id'],version=1))
        with self.assertRaises(ClientError):self.resume(OperatorClient(self.origin,grant_token=target['token']),handoff)
        listing=self.owner.request('POST','/api/apps/sample-one/agent-grants/handoff-list',{})
        self.assertEqual(listing['handoffs'][0]['effective_status'],'SOURCE_INVALID')

    def test_competing_grants_and_expired_handoffs_fail_closed(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=0),'existing-key')
        saved=self.create(job)
        a=self.grant('replacement',['handoff.resume','jobs.read'])
        b=self.grant('replacement',['handoff.resume','jobs.read'])
        clients=[OperatorClient(self.origin,grant_token=x['token']) for x in (a,b)]
        def claim(client):
            try:self.resume(client,saved);return True
            except ClientError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,clients))
        self.assertEqual(sum(results),1)
        other=self.create(job)
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_handoffs SET expires=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),other['id']))
        with self.assertRaises(ClientError):self.resume(clients[0],other)

    def test_foreign_jobs_and_changed_catalog_or_policy_are_rejected(self):
        foreign=enqueue(self.store,'sample-two','pipeline',dict(stage=1),'foreign-key')
        with self.assertRaises(ClientError):self.create(foreign)
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=2),'private-source')
        saved=self.create(job);target=self.grant('replacement',['handoff.resume','jobs.read'])
        client=OperatorClient(self.origin,grant_token=target['token'])
        with patch('mission_control.agent_handoffs.catalog',return_value={'catalog_sha256':'f'*64}):
            with self.assertRaises(ClientError):self.resume(client,saved)
        with patch('mission_control.agent_handoffs.operating_manifest',return_value={'changed':True}):
            with self.assertRaises(ClientError):self.resume(client,saved)
        self.assertEqual(self.resume(client,saved)['job_id'],job['id'])
        exported=json.dumps(self.store.export('sample-one'))
        self.assertNotIn('agent_handoffs',exported)
        self.assertNotIn(target['token'],exported)

    def test_recipient_expiry_and_handoff_source_expiry_deny(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=0),'preserved-key')
        saved=self.create(job);target=self.grant('replacement',['handoff.resume','jobs.read'])
        expired=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_grants SET expires=? WHERE id=?',(expired,target['grant']['id']))
        with self.assertRaises(ClientError):self.resume(OperatorClient(self.origin,grant_token=target['token']),saved)
        source=self.grant('source',['handoff.create','jobs.read'])
        value=dict(job_id=job['id'],recipient='replacement',operations=['jobs.read'],
                   expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat())
        saved=OperatorClient(self.origin,grant_token=source['token']).call(self.envelope('handoff.create',value))
        fresh=self.grant('replacement',['handoff.resume','jobs.read'])
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_grants SET expires=? WHERE id=?',(expired,source['grant']['id']))
        with self.assertRaises(ClientError):self.resume(OperatorClient(self.origin,grant_token=fresh['token']),saved)

    def test_referenced_record_revision_changes_invalidate_handoff(self):
        with connection(self.store.path) as db:
            db.execute('INSERT INTO records(id,app_id,kind,title,data,source,provenance,hash,version,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       ('record-one','sample-one','synthetic','Synthetic','{}','fixture','fixture','first',1,'2026-01-01'))
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=1,record_id='record-one',unknown_id='private-id'),'key')
        saved=self.create(job);target=self.grant('replacement',['handoff.resume','jobs.read'])
        self.assertEqual(saved['context']['resources']['checked_fields'],['record_id'])
        self.assertEqual(saved['context']['resources']['unverified_field_count'],1)
        self.assertNotIn('private-id',json.dumps(saved))
        with connection(self.store.path) as db:
            db.execute('UPDATE records SET version=2,hash=? WHERE id=?',('second','record-one'))
        listed=self.owner.request('POST','/api/apps/sample-one/agent-grants/handoff-list',{})['handoffs'][0]
        self.assertEqual(listed['context_status'],'CHANGED');self.assertIn('resources',listed['context_changes'])
        with self.assertRaises(ClientError):self.resume(OperatorClient(self.origin,grant_token=target['token']),saved)

    def test_handoff_rejects_more_than_100_referenced_resources(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=1,source_ids=['source-'+str(x) for x in range(101)]),'key')
        with self.assertRaises(ClientError):self.create(job)

    def test_report_projection_contains_only_scoped_safe_receipts(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=1),'private-report-key')
        saved=self.create(job);issued=self.grant('replacement',['handoff.resume','jobs.read'])
        with connection(self.store.path) as db:
            result=report_summary(db,'sample-one',datetime.now(timezone.utc))
            foreign=report_summary(db,'sample-two',datetime.now(timezone.utc))
        self.assertEqual(result['items'][0]['id'],saved['id']);self.assertEqual(result['items'][0]['job_id'],job['id'])
        self.assertEqual(result['items'][0]['status'],'READY');self.assertEqual(foreign['total'],0)
        self.assertNotIn('private-report-key',json.dumps(result));self.assertNotIn(issued['token'],json.dumps(result))
        self.assertNotIn('recipient',json.dumps(result));self.assertEqual(result['status_counts']['READY'],1)


if __name__=='__main__':unittest.main()
