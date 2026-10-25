"""Unified actual service/HTTP journeys, source drift and strict review boundaries."""
import copy
from datetime import datetime, timezone
from unittest.mock import patch
import unittest
from tests import test_http
from tests.test_aso_validation import listing
from tests.test_benchmark_context import records
from tests.test_benchmark_ads import saved_report, SEGMENT
from tests.test_customer_workflow import proposal
from tests.test_ledger import cohort, event
from tests.test_subscription_journey import bound
from tests.test_experiments import prepared, REGISTER
from tests.test_subscription_variants import configuration
from mission_control.common import Invalid, digest
from mission_control.growth_review_store import GrowthReviews
from mission_control.customer_workflow_store import CustomerWorkflows
from mission_control.experiments import Experiments
from mission_control.subscription_review import review_status, subscription_experiments, ads_sources, review_issues, source_recovery_issues


class SubscriptionReviewTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

    def configure(self):
        store = self.server.service.store
        app = store.app("sample-one")
        return store.save_app("sample-one", dict(app["data"], release="build-1", locale="en-US", currency="USD", store_app_id="123"), app["version"])

    def body(self):
        app = self.configure()
        return dict(id="listing-one", manifest_version=app["version"], kind="ASO_LISTING", data=dict(release="build-1", listing=listing()))

    def reference(self, version):
        ref, _ = records()
        ref.update(period_start="2026-10-01T00:00:00+00:00", period_end="2026-10-08T00:00:00+00:00", published_at="2026-10-10T00:00:00+00:00", retrieved_at="2026-10-22T00:00:00+00:00")
        return dict(id="reference-one", manifest_version=version, kind="BENCHMARK_REFERENCE", data=dict(release="build-1", reference=ref))

    def test_review_api_and_workspace_expose_three_separate_evidence_states(self):
        self.configure()
        route = "/api/apps/sample-one/subscription-growth"
        code, value, _ = self.request(route)
        self.assertEqual(code, 200)
        self.assertEqual(value["schema"], "growth.subscription-review.v1")
        self.assertEqual(set(value["evidence_states"]), {"local_evidence", "provider_verification", "outcomes"})
        self.assertEqual(value["status"], "NEEDS_INPUT")
        self.assertFalse(value["external_writes"])
        self.assertEqual(value["spend_minor"], 0)
        self.assertEqual(value["source_hash"], digest({key:item for key,item in value.items() if key != "source_hash"}))
        workspace = self.request("/api/apps/sample-one")[1]
        self.assertEqual(workspace["subscription_growth"]["app_id"], "sample-one")
        self.assertEqual(self.request(route + "?as_of=2999")[0], 400)
        self.assertEqual(self.request(route + "/extra")[0], 404)
        self.assertEqual(self.request("/api/apps/missing/subscription-growth")[0], 404)

    def test_customer_and_account_recovery_use_exact_ids_without_raw_sources(self):
        customers = dict(history=[dict(id='expired-workflow',data='PRIVATE_EXCERPT',readout=dict(status='SOURCE_REVIEW_NEEDED')),
                                 dict(id='stale-workflow',readout=dict(status='STALE_APP_SCOPE')),
                                 dict(id='current-workflow',readout=dict(status='HYPOTHESIS_READY_FOR_REVIEW'))])
        sources = [dict(job_id='invalid-account',state='SOURCE_REVIEW_NEEDED',reason='PRIVATE_DIAGNOSTIC'),
                   dict(job_id='current-account',state='CURRENT_SAVED_SOURCE')]
        issues = source_recovery_issues(customers,sources)
        self.assertEqual([(r['area'],r['id'],r['code']) for r in issues],
            [('customer_evidence','expired-workflow','SOURCE_REVIEW_NEEDED'),
             ('customer_evidence','stale-workflow','STALE_APP_SCOPE'),
             ('benchmarks','invalid-account','SOURCE_REVIEW_NEEDED')])
        self.assertNotIn('PRIVATE',str(issues))
        self.assertEqual(source_recovery_issues(dict(history=customers['history'][2:]),sources[1:]),[])

    def test_real_expired_removed_and_stale_customer_workflows_require_recovery(self):
        app = self.configure();store=self.server.service.store
        work=CustomerWorkflows(store,lambda:datetime(2026,10,23,tzinfo=timezone.utc))
        value=proposal();value['sources'][0]['expires_at']='2026-10-24T00:00:00+00:00'
        work.save('sample-one',dict(id='customer-one',manifest_version=app['version'],data=value))
        current=review_status(store,'sample-one',lambda:datetime(2026,10,23,tzinfo=timezone.utc))
        self.assertFalse(any(r['area']=='customer_evidence' for r in current['issues']))
        expired=review_status(store,'sample-one',lambda:datetime(2026,10,24,tzinfo=timezone.utc))
        self.assertIn(('customer-one','SOURCE_REVIEW_NEEDED'),[(r.get('id'),r['code']) for r in expired['issues']])
        self.assertEqual(expired['status'],'NEEDS_INPUT')
        value['sources'][0]['availability']='REMOVED'
        work.save('sample-one',dict(id='removed-one',manifest_version=app['version'],data=value))
        code,readback,_=self.request('/api/apps/sample-one/subscription-growth')
        self.assertEqual(code,200)
        self.assertIn(('removed-one','SOURCE_REVIEW_NEEDED'),[(r.get('id'),r['code']) for r in readback['issues']])
        store.save_app('sample-one',dict(app['data'],release='changed-build'),app['version'])
        stale=review_status(store,'sample-one',lambda:datetime(2026,10,23,tzinfo=timezone.utc))
        self.assertIn(('customer-one','STALE_APP_SCOPE'),[(r.get('id'),r['code']) for r in stale['issues']])
        self.assertEqual(len(stale['customer_workflows']['history']),2)

    def test_fully_populated_review_stays_available_only_with_current_sources(self):
        growth=dict(history=[dict(id=kind,kind=kind,readout=dict(analysis=dict(status='READY_FOR_REVIEW'),availability='CURRENT_LOCAL_EVIDENCE'))
                             for kind in ('ASO_LISTING','BENCHMARK_REFERENCE','BENCHMARK_COMPARISON')])
        customer=dict(history=[dict(id='workflow-one',readout=dict(status='HYPOTHESIS_READY_FOR_REVIEW'))])
        experiments=[dict(current_source_findings=[])]
        sources=[dict(job_id='report-one',state='CURRENT_SAVED_SOURCE')]
        self.assertEqual(review_issues(growth,[{}],experiments,customer,sources),[])
        customer['history'][0]['readout']['status']='SOURCE_REVIEW_NEEDED'
        self.assertTrue(review_issues(growth,[{}],experiments,customer,sources))
        customer['history'][0]['readout']['status']='HYPOTHESIS_READY_FOR_REVIEW'
        sources[0]['state']='SOURCE_REVIEW_NEEDED'
        self.assertTrue(review_issues(growth,[{}],experiments,customer,sources))

    def test_entry_http_csrf_exact_shape_duplicate_json_and_immutable_replay(self):
        body = self.body()
        route = "/api/apps/sample-one/subscription-growth/entries"
        self.assertEqual(self.request(route, body, headers={"X-CSRF-Token":"wrong"})[0], 403)
        self.assertEqual(self.request(route + "?approve=true", body)[0], 400)
        self.assertEqual(self.request(route + "/execute", body)[0], 400)
        self.assertEqual(self.request(route, dict(body, approve=True))[0], 400)
        self.assertEqual(self.request(route, raw=b'{"id":"one","id":"two"}')[0], 400)
        code, row, _ = self.request(route, body)
        self.assertEqual(code, 201)
        self.assertEqual(self.request(route, body)[1], row)
        bad = copy.deepcopy(body)
        bad["data"]["listing"]["fields"]["title"] = "Different source"
        self.assertEqual(self.request(route, bad)[0], 400)
        history = self.request("/api/apps/sample-one/subscription-growth/history")[1]
        self.assertEqual(history["history"][0]["hash"], row["hash"])
        self.assertEqual(self.request("/api/apps/sample-one/subscription-growth/history?all=true")[0], 400)

    def test_unified_journeys_benchmarks_customer_sources_and_local_notes(self):
        app = self.configure()
        store, service = self.server.service.store, self.server.service
        service.cohort("sample-one", cohort())
        service.events("sample-one", dict(cohort_id="pilot-1", events=[event("install", "INSTALL"), bound("trial", "TRIAL_START"), bound("paid", "PURCHASE", day="2026-09-05", amount=1000)]))
        CustomerWorkflows(store).save("sample-one", dict(id="workflow-one", manifest_version=app["version"], data=proposal()))
        _, report = saved_report(store)
        route = "/api/apps/sample-one/subscription-growth/entries"
        self.assertEqual(self.request(route, dict(id="listing-one", manifest_version=app["version"], kind="ASO_LISTING", data=dict(release="build-1", listing=listing())))[0], 201)
        code, reference, _ = self.request(route, self.reference(app["version"]))
        self.assertEqual(code, 201)
        comparison = dict(id="comparison-one", manifest_version=app["version"], kind="BENCHMARK_COMPARISON", data=dict(reference_id=reference["id"], reference_hash=reference["hash"], job_id="job-one", report_hash=report["source_hash"], metric="CPT_MINOR", segment=SEGMENT))
        self.assertEqual(self.request(route, comparison)[0], 201)
        value = self.request("/api/apps/sample-one/subscription-growth")[1]
        self.assertEqual(len(value["journeys"]), 1)
        self.assertEqual(len(value["journeys"][0]["journey"]["groups"]), 1)
        self.assertEqual(len(value["customer_workflows"]["history"]), 1)
        self.assertEqual(value["ads_sources"][0]["state"], "CURRENT_SAVED_SOURCE")
        row = next(row for row in value["history"]["history"] if row["kind"] == "BENCHMARK_COMPARISON")
        self.assertEqual(row["readout"]["analysis"]["difference"], 100)
        self.assertFalse(row["readout"]["analysis"]["classification_provider_verified"])
        note = dict(id="note-one", manifest_version=app["version"], kind="EDITORIAL_NOTE", data=dict(target_id=reference["id"], target_hash=reference["hash"], decision="KEEP", rationale="Keep the supplied reference for local review"))
        self.assertEqual(self.request(route, note)[0], 201)
        self.assertEqual(self.request("/api/apps/sample-two/subscription-growth/entries", note)[0], 400)
        note["data"]["decision"] = "APPROVED"
        self.assertEqual(self.request(route, dict(note, id="not-approval"))[0], 400)

    def test_source_drift_suppresses_previously_comparable_difference(self):
        app = self.configure()
        store = self.server.service.store
        record, report = saved_report(store)
        work = GrowthReviews(store)
        ref = work.save("sample-one", self.reference(app["version"]))
        row = work.save("sample-one", dict(id="comparison-one", kind="BENCHMARK_COMPARISON", manifest_version=app["version"], data=dict(reference_id=ref["id"], reference_hash=ref["hash"], job_id="job-one", report_hash=report["source_hash"], metric="CPT_MINOR", segment=SEGMENT)))
        store.save_record("sample-one", dict(record, manifest_version=app["version"], data=dict(record["data"], account_id="999")))
        value = self.request("/api/apps/sample-one/subscription-growth")[1]
        readout = next(item for item in value["history"]["history"] if item["id"] == row["id"])["readout"]
        self.assertEqual(readout["availability"], "SOURCE_REVIEW_NEEDED")
        self.assertIsNone(readout["analysis"]["difference"])
        self.assertEqual(value["ads_sources"][0]["state"], "SOURCE_REVIEW_NEEDED")
        self.assertIn(('benchmarks','job-one','SOURCE_REVIEW_NEEDED'),
            [(item['area'],item.get('id'),item['code']) for item in value['issues']])
        self.assertEqual(value['status'],'NEEDS_INPUT')

    def test_review_status_detects_app_change_during_sequential_read(self):
        original = self.configure()
        store = self.server.service.store
        actual = CustomerWorkflows.list
        def change(instance, app_id):
            app = store.app(app_id)
            store.save_app(app_id, dict(app["data"], release="changed-build"), app["version"])
            return actual(instance, app_id)
        with patch("mission_control.subscription_review.CustomerWorkflows.list", change):
            with self.assertRaises(Invalid):
                review_status(store, "sample-one")
        with self.assertRaises(Invalid):
            self.server.service.subscription_review("sample-one", expected=original)

    def test_subscription_experiments_expose_current_configuration_drift(self):
        self.configure()
        store = self.server.service.store
        plan = prepared(store)
        sources = {}
        for arm in ("control", "treatment"):
            config = configuration(arm)
            record = store.save_record("sample-one", dict(kind="billing", title="Synthetic billing source", source="Synthetic fixture only",
                data=dict(release="build-1", platform="iOS", locale="en-US", result="PASS", sku=config["product_id"], currency="USD", price_minor=1000,
                          restore_tested=True, trial_eligibility_tested=True, eligibility_status="ELIGIBLE", checked_at=REGISTER, expires_at="2026-11-01T00:00:00+00:00", subscription_configuration=config)))
            sources[arm] = record
            plan[arm] = dict(variant_type="SUBSCRIPTION", cohort_id="experiment-" + arm, source_record_id=record["id"], configuration=config)
        with patch("mission_control.experiments.now", return_value=REGISTER):
            row = Experiments(store).create("sample-one", plan)
        value = self.request("/api/apps/sample-one/subscription-growth")[1]
        self.assertEqual(value["experiments"][0]["id"], row["id"])
        self.assertEqual(value["experiments"][0]["current_source_findings"], [])
        record = sources["control"]
        store.save_record("sample-one", dict(record, data=dict(record["data"], result="FAIL")))
        result = subscription_experiments(store, store.app("sample-one"), "2026-10-23T00:00:00+00:00")
        self.assertEqual(result[0]["review_state"], "SOURCE_REVIEW_NEEDED")
