"""Protected-context lifecycle using temporary SQLite and synthetic external observations."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.agent_grants import Grants
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.operation_authority import bound_agent, bound_owner, protected
from mission_control.operation_catalog import OPERATIONS, descriptor
from mission_control.organic_video_collector import claim, prepare, submit
from mission_control.review_access import Access
from mission_control.store import Store
from tests.test_organic_video_discovery import bundle


class Identities:
    def local(self, session, principal, generation=None):
        if session != 'owner-session' or principal != 'github:123' or generation not in (None, 1):
            raise PermissionError('Synthetic owner session changed')
        return {'session_generation': 1}


class FakeExternalAgent:
    """Represent an external read-capable agent without contacting a provider."""
    def __init__(self):
        self.reads = []

    def collect(self, saved, claimed):
        self.reads.append((saved['task']['query']['genre'], claimed['claim_id']))
        value = bundle(saved['task'])
        value.update(task_id=saved['id'], task_hash=saved['task_hash'], claim_id=claimed['claim_id'])
        return {'task_id': saved['id'], 'result': value}


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'test.sqlite3')
        self.owner = {'principal': 'github:123', 'login': 'owner'}
        Access(self.store).bootstrap('sample-one', self.owner, {'confirm_owner': True})
        additions = {
            'organic-video.claim': descriptor('POST', '/unused', 'LOCAL', ('task_id', 'task_hash')),
            'organic-video.submit': descriptor('POST', '/unused', 'LOCAL', ('task_id', 'result')),
        }
        self.catalog = patch.dict(OPERATIONS, additions)
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        self.grants = Grants(self.store)
        self.expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        self.grant = self.grants.issue('sample-one', self.owner,
            {'agent_id': 'personal-agent', 'manifest_version': 1, 'expires': self.expires,
             'operations': list(additions), 'max_calls': 100})
        self.body = {'request_id': 'request-one',
            'query': {'genre': 'personal growth', 'app_type': 'AI life coach', 'search_terms': 'habits'},
            'policy': {'recipient_grant_id': self.grant['grant']['id'], 'platforms': ['tiktok'],
                       'hosts': ['www.tiktok.com'], 'expires': self.expires, 'max_candidates': 5,
                       'max_reads': 100, 'max_seconds': 600, 'access': 'PUBLIC_WEB'}}

    def owner_call(self, body=None, app='sample-one', actor=None):
        body = self.body if body is None else body
        envelope = {'app_id': app, 'operation': 'organic-video.prepare', 'input': body}
        with bound_owner(self.store, envelope, Identities(), 'owner-session', self.owner):
            with protected(self.store, envelope) as admitted:
                return prepare(self.store, app, actor or admitted, body)

    def agent_call(self, operation, body, function, token=None, app='sample-one', actor=None):
        envelope = {'app_id': app, 'operation': operation, 'input': body}
        admission = self.grants.admit(token or self.grant['token'], envelope)
        with bound_agent(self.store, envelope, admission):
            with protected(self.store, envelope) as admitted:
                return function(self.store, app, actor or admitted, body)

    def claim_task(self, saved):
        return self.agent_call('organic-video.claim', {'task_id': saved['id'], 'task_hash': saved['task_hash']}, claim)

    def submission(self, saved, claimed, count=10):
        value = bundle(saved['task'], count)
        value.update(task_id=saved['id'], task_hash=saved['task_hash'], claim_id=claimed['claim_id'])
        return {'task_id': saved['id'], 'result': value}

    def test_external_agent_claims_submits_and_replay_is_stable(self):
        saved = self.owner_call()
        self.assertEqual(saved['status'], 'READY')
        self.assertEqual(saved['task']['collection'], 'NOT_RUN')
        self.assertEqual(saved['task']['boundaries']['wmm_credentials'], 'NOT_DELEGATED')
        self.assertEqual(saved['task']['boundaries']['tool_enforcement'], 'EXTERNAL_AGENT')
        self.assertEqual(self.owner_call()['id'], saved['id'])
        claimed = self.claim_task(saved)
        self.assertEqual(claimed['status'], 'CLAIMED')
        self.assertEqual(self.claim_task(saved)['claim_id'], claimed['claim_id'])
        agent = FakeExternalAgent()
        request = agent.collect(saved, claimed)
        self.assertEqual(agent.reads, [('personal growth', claimed['claim_id'])])
        complete = self.agent_call('organic-video.submit', request, submit)
        self.assertEqual(complete['status'], 'SUBMITTED')
        self.assertEqual(complete['result']['collection_verification'], 'REQUIRED')
        self.assertEqual(self.agent_call('organic-video.submit', request, submit), complete)
        changed = copy.deepcopy(request); changed['result']['read_count'] = 2
        with self.assertRaises(Invalid): self.agent_call('organic-video.submit', changed, submit)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_discovery_tasks').fetchone()[0], 1)

    def test_missing_baseline_and_source_failures_stay_incomplete(self):
        saved = self.owner_call(); claimed = self.claim_task(saved)
        request = self.submission(saved, claimed, count=9)
        request['result']['failures'] = [{'source': 'https://www.tiktok.com/@creator', 'code': 'LOGIN'}]
        result = self.agent_call('organic-video.submit', request, submit)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['result']['items'][0]['status'], 'INSUFFICIENT_BASELINE')
        self.assertEqual(result['result']['source_failures'][0]['code'], 'LOGIN')

    def test_identity_scope_grant_revocation_and_claim_expiry_are_enforced(self):
        with self.assertRaises(PermissionError): prepare(self.store, 'sample-one', self.owner['principal'], self.body)
        with self.assertRaises(PermissionError): self.owner_call(actor='github:forged')
        saved = self.owner_call(); claimed = self.claim_task(saved)
        request = self.submission(saved, claimed)
        with self.assertRaises(PermissionError):
            self.agent_call('organic-video.submit', request, submit, app='sample-two')
        with connection(self.store.path) as db:
            db.execute("UPDATE organic_discovery_tasks SET claim_until=? WHERE id=?",
                       ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), saved['id']))
        with self.assertRaises(PermissionError): self.agent_call('organic-video.submit', request, submit)
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_grants SET status='REVOKED',version=version+1 WHERE id=?", (self.grant['grant']['id'],))
        with self.assertRaises(PermissionError): self.claim_task(saved)

    def test_conflicting_or_unclaimed_results_are_rejected(self):
        saved = self.owner_call()
        forged = {'task_id': saved['id'], 'result': {'task_id': saved['id'], 'claim_id': 'invented'}}
        with self.assertRaises(PermissionError): self.agent_call('organic-video.submit', forged, submit)
        claimed = self.claim_task(saved)
        result = self.submission(saved, claimed)
        result['result']['execution'] = 'SAVED_POOL'
        with self.assertRaises(Invalid): self.agent_call('organic-video.submit', result, submit)
        changed = copy.deepcopy(self.body); changed['query']['genre'] = 'different'
        with self.assertRaises(Invalid): self.owner_call(changed)

    def test_app_revision_and_saved_result_tampering_fail_closed(self):
        saved = self.owner_call(); claimed = self.claim_task(saved)
        request = self.submission(saved, claimed)
        with connection(self.store.path) as db:
            db.execute("UPDATE apps SET version=version+1 WHERE id='sample-one'")
        with self.assertRaises(PermissionError):
            self.agent_call('organic-video.submit', request, submit)
        with connection(self.store.path) as db:
            db.execute("UPDATE apps SET version=version-1 WHERE id='sample-one'")
        done = self.agent_call('organic-video.submit', request, submit)
        self.assertEqual(done['status'], 'SUBMITTED')
        with connection(self.store.path) as db:
            db.execute("UPDATE organic_discovery_tasks SET result='{}' WHERE id=?", (saved['id'],))
        with self.assertRaises(Invalid):
            self.agent_call('organic-video.submit', request, submit)

    def test_another_valid_grant_cannot_claim_or_submit_the_task(self):
        saved = self.owner_call()
        other = self.grants.issue('sample-one', self.owner,
            {'agent_id': 'other-agent', 'manifest_version': 1, 'expires': self.expires,
             'operations': ['organic-video.claim', 'organic-video.submit'], 'max_calls': 20})
        body = {'task_id': saved['id'], 'task_hash': saved['task_hash']}
        with self.assertRaises(PermissionError):
            self.agent_call('organic-video.claim', body, claim, token=other['token'])
        claimed = self.claim_task(saved)
        with self.assertRaises(PermissionError):
            self.agent_call('organic-video.submit', self.submission(saved, claimed), submit, token=other['token'])

    def test_old_observations_cannot_be_relabelled_as_a_fresh_collection(self):
        saved = self.owner_call(); claimed = self.claim_task(saved)
        request = self.submission(saved, claimed)
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        source = request['result']['candidates'][0]
        source['history'][0]['observed_at'] = old
        from mission_control.common import digest
        source['evidence'][1]['observed_at'] = old
        source['evidence'][1]['observation_hash'] = digest(source['history'][0])
        with self.assertRaisesRegex(Invalid, 'after the claim'):
            self.agent_call('organic-video.submit', request, submit)


if __name__ == '__main__':
    unittest.main()
