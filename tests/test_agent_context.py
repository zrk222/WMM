"""Selected-app source privacy, bounds and current readiness derivation."""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.agent_context import snapshot
from mission_control.agent_contract import draft,prompt
from mission_control.common import Invalid, canonical
from mission_control.store import Store
from mission_control.db import connection


class ContextTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.store=Store(Path(folder.name)/'context.sqlite3')

    def test_snapshot_stage_source_public_facts_and_no_private_manifest(self):
        app=self.store.app('sample-one')
        app['data'].update(brand_source='Owner theme',conversation='PRIVATE_CONVERSATION')
        with patch.object(self.store,'app',return_value=app):value=snapshot(self.store,'sample-one')
        text=canonical(value)
        self.assertEqual(len(value['sources']),17)
        self.assertEqual(value['sources'][0]['data']['brand_source'],'Owner theme')
        self.assertNotIn('PRIVATE_CONVERSATION',text)
        self.assertEqual(value['sources'][0]['data']['authorized_spend_minor'],0)
        self.assertTrue(all(s['data']['access']=='NOT_CHECKED' for s in value['sources'] if s['id'] in ('release_observation','subscription_observation')))

    def test_saved_sources_excludes_review_text_and_private_locations(self):
        self.store.save_record('sample-one',dict(kind='review',title='PRIVATE REVIEW',source='PRIVATE SOURCE',
            data=dict(confirmed=True,severity='P0',text='PRIVATE CUSTOMER')))
        value=snapshot(self.store,'sample-one')
        self.assertNotIn('PRIVATE',canonical(value))
        stage=next(s for s in value['sources'] if s['id']=='stage_5')
        self.assertEqual(stage['data']['status'],'BLOCKED')
        self.assertGreater(stage['data']['missing_count'],0)

    def test_other_app_and_agent_jobs_cannot_change_context(self):
        before=snapshot(self.store,'sample-one')
        self.store.save_record('sample-two',dict(kind='claim',title='Private other app',source='OTHER_APP',data=dict(result='FAIL')))
        with connection(self.store.path) as db:
            db.execute("INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES('synthetic','sample-one','agent_run','{}','RUNNING','now','now','synthetic')")
        self.assertEqual(snapshot(self.store,'sample-one'),before)

    def test_record_change_invalidates_fingerprint_without_raw_content(self):
        before=snapshot(self.store,'sample-one')
        self.store.save_record('sample-one',dict(kind='claim',title='PRIVATE TITLE',source='PRIVATE URL',data=dict(result='FAIL',release='other')))
        after=snapshot(self.store,'sample-one')
        self.assertNotEqual(after['evidence_fingerprint'],before['evidence_fingerprint'])
        self.assertNotIn('PRIVATE',canonical(after))

    def test_indexed_and_snapshot_overflow_offer_repair(self):
        with patch('mission_control.agent_context.LIMIT',0),self.assertRaisesRegex(Invalid,'narrow or archive'):
            self.store.save_record('sample-one',dict(kind='claim',title='Synthetic',source='Synthetic',data={}))
            snapshot(self.store,'sample-one')
        with patch('mission_control.agent_context.MAX_CHARS',100),self.assertRaisesRegex(Invalid,'shorten public'):
            snapshot(self.store,'sample-one')

    def test_citations_require_exact_approved_sources(self):
        value=dict(summary='Plan',items=[dict(title='Test',detail='Proposed',source_ids=['stage_2','app_manifest'])],unknowns=[])
        self.assertEqual(draft(value,('stage_2','app_manifest')),value)
        with self.assertRaises(Invalid):draft(value,('app_manifest',))

    def test_prompt_utf8_boundary_is_checked_before_any_model_request(self):
        app=self.store.app('sample-one')
        context=dict(sources=[dict(id='app_manifest',data='界'*11000)])
        with self.assertRaisesRegex(Invalid,'shorten public facts'):
            prompt(app,'campaign_plan',context=context)

    def test_provider_source_preserves_pending_then_latest_failure(self):
        from tests.test_release_pipeline import ReleasePipeline, observed
        helper=ReleasePipeline();helper.setUp();self.addCleanup(helper.tearDown)
        job=helper.queue_read(observed('WAITING_FOR_REVIEW'));helper.select(job)
        first=snapshot(helper.store,'sample-one')
        release=next(s for s in first['sources'] if s['id']=='release_observation')
        self.assertEqual(release['data']['state'],'REVIEW_PENDING')
        self.assertEqual(release['data']['access'],'NOT_CHECKED')
        helper.queue_read(failure=Invalid('PRIVATE PROVIDER DIAGNOSTIC'))
        latest=snapshot(helper.store,'sample-one')
        release=next(s for s in latest['sources'] if s['id']=='release_observation')
        self.assertEqual(release['data']['state'],'READ_BLOCKED')
        self.assertNotIn('PRIVATE',canonical(latest))
        self.assertNotEqual(first['evidence_fingerprint'],latest['evidence_fingerprint'])


if __name__=='__main__':unittest.main()
