"""Actual SQLite plans and scoped analytics retention/quota regression at synthetic scale."""
from contextlib import contextmanager
import json
import time
import unittest
from unittest.mock import patch
from mission_control import insights as module
from mission_control.common import Invalid, canonical, digest, now, uid
from mission_control.db import connection
from mission_control.insights_transport import ProviderFailure
import tests.test_measurement_connectors as fixtures


class AnalyticsReadIndexTests(unittest.TestCase):
    setUp = fixtures.MeasurementTests.setUp
    create = fixtures.MeasurementTests.create

    def test_idempotent_schema_and_actual_query_plans_use_scoped_indexes(self):
        from mission_control.db import initialize
        initialize(self.store.path);initialize(self.store.path)
        checks=[('SELECT id FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid DESC LIMIT 100',('sample-one','synthetic'),'insight_report_source'),
                ('SELECT COUNT(*)FROM insight_requests WHERE scope_key=? AND attempted>?',('scope',0),'insight_request_scope_time'),
                ('DELETE FROM insight_requests WHERE attempted<?',(0,),'insight_request_time')]
        plans=[]
        with connection(self.store.path)as db:
            for sql,args,index in checks:
                details=[row['detail']for row in db.execute('EXPLAIN QUERY PLAN '+sql,args)]
                self.assertTrue(any(index in line for line in details),(sql,details))
                self.assertFalse(any('USE TEMP B-TREE'in line for line in details),details)
                plans.append(dict(sql=sql,index=index,details=details))
        print('ANALYTICS_QUERY_PLANS '+json.dumps(plans,sort_keys=True))

    def test_non_clarity_reads_skip_quota_count_but_retain_attempt_and_expiry_cleanup(self):
        statements=[];original=module.connection
        @contextmanager
        def observed(path):
            with original(path)as db:
                db.set_trace_callback(statements.append)
                yield db
        with patch.object(module,'connection',observed):
            sid=self.create()['source_id']
            with patch('mission_control.insights_transport.request',side_effect=lambda *args:{'id':123}if args[0].endswith('/123/')else{'results':[]}):
                self.assertEqual(self.insights.refresh('sample-one',sid,{'confirm_read':True})['status'],'CONNECTED')
        count_queries=[sql for sql in statements if 'COUNT(*)'in sql.upper()and 'INSIGHT_REQUESTS'in sql.upper()]
        self.assertEqual(count_queries,[],'PostHog has no local daily cap; do not count its rolling attempt history')
        with connection(self.store.path)as db:
            self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_requests').fetchone()[0],2)
            db.execute('INSERT INTO insight_requests(scope_key,attempted)VALUES(?,?)',('expired',0))
        self.insights.reserve_candidate_read('another-synthetic-scope','revenuecat')
        with connection(self.store.path)as db:
            self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_requests WHERE attempted=0').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_requests').fetchone()[0],3)

    def test_clarity_same_scope_limit10_includes_failures_and_does_not_block_another_scope(self):
        for _ in range(10):self.insights.reserve_candidate_read('scope-one','clarity')
        with self.assertRaises(ProviderFailure)as failure:self.insights.reserve_candidate_read('scope-one','clarity')
        self.assertEqual(failure.exception.code,'LOCAL_RATE_LIMITED')
        self.insights.reserve_candidate_read('scope-two','clarity')
        with connection(self.store.path)as db:
            self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_requests WHERE scope_key=?',('scope-one',)).fetchone()[0],10)
            self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_requests WHERE scope_key=?',('scope-two',)).fetchone()[0],1)

    def test_scaled_scope_history_keeps_latest100_and_preserves_other_source(self):
        sid=self.create()['source_id'];self.create('revenuecat')
        with connection(self.store.path)as db:
            row=self.insights.row(db,'sample-one',sid)
            other=db.execute("SELECT id FROM insight_sources WHERE app_id=? AND provider='revenuecat'",('sample-one',)).fetchone()[0]
            for index in range(5000):
                data=dict(synthetic_index=index)
                db.execute('INSERT INTO insight_reports VALUES(?,?,?,?,?,?,?)',('sample-one',uid(),other,'revenuecat',canonical(data),digest(data),now()))
            for index in range(1000):
                data=dict(synthetic_index=index)
                db.execute('INSERT INTO insight_reports VALUES(?,?,?,?,?,?,?)',('sample-one',uid(),sid,'posthog',canonical(data),digest(data),now()))
            before=db.execute('SELECT COUNT(*)FROM insight_reports WHERE source_id=?',(other,)).fetchone()[0]
            started=time.monotonic();self.insights.report(db,'sample-one',row,dict(synthetic_index=1000));elapsed=time.monotonic()-started
            retained=[json.loads(r['data'])for r in db.execute('SELECT data FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid',('sample-one',sid))]
            self.assertEqual([r['synthetic_index']for r in retained],list(range(901,1001)))
            self.assertEqual(retained[-1]['source_version'],row['version']);self.assertEqual(retained[-1]['configuration_hash'],row['hash'])
            self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_reports WHERE source_id=?',(other,)).fetchone()[0],before)
            print('ANALYTICS_SCOPED_HISTORY '+json.dumps(dict(other_source_reports=before,selected_source_reports=100,trim_seconds=elapsed)))

    def test_stage_candidate_read_candidate_activate_candidate_check_stage_preserve_original_until_success(self):
        from mission_control.insights_contract import config
        sid=self.create()['source_id'];body={**fixtures.setup_body(),'version':1};data=config(fixtures.setup_body())
        candidate,old=self.insights.stage_candidate('sample-one',data,body)
        self.assertEqual(self.insights.list('sample-one')['sources'][0]['version'],1)
        with patch('mission_control.insights_transport.request',side_effect=fixtures.copy.deepcopy(fixtures.payloads()['posthog'])):
            result=self.insights.read_candidate('sample-one',candidate,data)
        self.insights.activate_candidate('sample-one',candidate,data,body,result)
        self.assertEqual(self.insights.list('sample-one')['sources'][0]['version'],2)
        with connection(self.store.path)as db:
            row=self.insights.row(db,'sample-one',sid)
            with self.assertRaises(Invalid):self.insights.check_stage(db,'sample-one',candidate['scope'],row,1)
        self.assertTrue(self.insights.events_editable(row))
        self.assertFalse(self.insights.events_editable(dict(row,status='DISCONNECTED')))
        self.insights.retire('sample-one',old)

    def test_discard_candidate_cleanup_unbound_cleanup_source_and_candidate_failure_keep_active_source(self):
        from mission_control.insights_contract import config
        sid=self.create()['source_id'];data=config(fixtures.setup_body())
        candidate,old=self.insights.stage_candidate('sample-one',data,{**fixtures.setup_body(),'version':1})
        fixtures.FakeVault.fail_delete=1
        self.assertTrue(self.insights.discard_candidate('sample-one',candidate))
        message=self.insights.candidate_failure(old,Invalid('synthetic-private-key'),True)
        self.assertIn('Replacement not activated',message);self.assertNotIn('synthetic-private-key',message)
        self.insights.cleanup_source('sample-one',sid)
        with connection(self.store.path)as db:self.assertEqual(db.execute('SELECT COUNT(*)FROM insight_cleanup').fetchone()[0],0)
        self.insights.cleanup_unbound('sample-one')
        self.assertEqual(self.insights.list('sample-one')['sources'][0]['version'],1)
