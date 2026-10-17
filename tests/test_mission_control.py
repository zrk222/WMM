"""Behavioral proofs for persistent workspaces, pipeline and review boundaries."""
import copy
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest, amount, fraction, identifier, iso_time, now, required, safe_data, uid
from mission_control.db import connection, initialize
from mission_control.store import Store, decode, app_data, audit
from mission_control.service import Service, validate_evidence, validate_values, validate_binding
from mission_control.pipeline import evaluate, execute, current, checks_by_kind, missing_manifest, missing_evidence, critical_findings
from mission_control.packets import creative, reflection, weekly, stage_packet, by_kind
from mission_control.metrics import cohort_metrics, retention_metrics, acquisition_metrics, summarize, ratio
from mission_control.providers import credential, sync, NoRedirect, read_json, scope_payload
from mission_control.worker import Runner, enqueue, jobs, claim, process, run_once, json_job
from mission_control.catalog import FIELDS, stages

STAMP=now()


def evidence_data(kind):
    """Construct explicit synthetic records to exercise all twelve stages."""
    data={field:"Synthetic acceptance" for field in FIELDS[kind]}
    data.update(release="test-build",result="PASS",checked_at=now(),locale="en-US")
    for field in ("authentic","rights_cleared","consent_review","refund_reconciliation","installed","fresh_install","signed_out","restore_tested","trial_eligibility_tested","mature","confirmed"):
        if field in data:data[field]=True
    for field in ("budget_minor","daily_cap_minor","price_minor","p0_count"):
        if field in data:data[field]=0
    if kind=="cohort":
        data.update(cohort_id="SYNTHETIC",currency="USD",installs=100,activated=50,paid=10,mature=True,acquisition_cost_minor=1000,net_proceeds_minor=5000,delivery_cost_minor=500,refunds_minor=0,horizon="D30")
    if kind=="retention":data.update(eligible=50,retained=20,window="D30",mature=True)
    if kind=="store":data.update(destination="https://example.com/store",availability="AVAILABLE")
    if kind=="asset":data.update(file_id="11111111-1111-1111-1111-111111111111.png",sha256="a"*64)
    if kind=="readiness":
        from tests.journey_fixtures import covered
        data.update(covered())
    return data


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"state.sqlite")
        self.service=Service(self.store,"maker")
        self.app=self.store.save_app("test-app",dict(name="Synthetic App",job="Practice",audience="Test audience",activation="Useful saved result",release="test-build",locale="en-US",currency="USD"))

    def tearDown(self):
        self.tmp.cleanup()

    def record(self,kind,data=None):
        return self.store.save_record("test-app",{"kind":kind,"title":"Synthetic "+kind,"source":"Synthetic fixture; not live evidence","data":data or evidence_data(kind)})

    def test_registry_persistence_and_version_conflict(self):
        self.assertEqual(len(self.store.apps()),4)
        data=dict(self.app["data"],job="Updated job")
        saved=self.store.save_app("test-app",data,1)
        self.assertEqual(saved["version"],2)
        with self.assertRaises(Invalid):self.store.save_app("test-app",data,1)
        restarted=Store(self.store.path)
        self.assertEqual(restarted.app("test-app")["data"]["job"],"Updated job")
        self.assertEqual(len(restarted.apps()),4)
        self.assertTrue(self.store.history("test-app"))

    def test_evidence_isolation_hash_and_conflict(self):
        record=self.record("claim")
        self.assertEqual(len(self.store.records("sample-one")),0)
        body=dict(record,title="Changed title")
        with self.assertRaises(Invalid):self.store.save_record("sample-one",body)
        saved=self.store.save_record("test-app",body)
        self.assertEqual(saved["version"],2)
        self.assertEqual(saved["hash"],record["hash"])
        with self.assertRaises(Invalid):self.store.save_record("test-app",body)
        self.assertEqual(digest({"kind":saved["kind"],"data":saved["data"],"source":saved["source"]}),saved["hash"])

    def test_all_stages_with_explicit_inputs(self):
        kinds={kind for stage in stages() for kind in stage["inputs"] if kind!="manifest"}
        for kind in kinds:self.record(kind)
        records=self.store.records("test-app")
        checklist=evaluate(self.app,records)
        self.assertEqual(len(checklist),12)
        self.assertTrue(all(s["status"]=="READY" for s in checklist))
        output=execute(self.app,records,0)
        self.assertEqual(len(output["outputs"]),12)
        self.assertEqual(len(output["outputs"][5]["packet"]["content"]["briefs"]),6)
        self.assertEqual(output["outputs"][11]["packet"]["content"]["status"],"PROPOSED")
        self.assertEqual(output["external_execution"],"NOT_RUN")
        self.assertEqual(output["spend_minor"],0)
        for item in output["outputs"]:
            operations=item["packet"]["operations"]
            self.assertGreaterEqual(len(operations["tasks"]),3)
            self.assertTrue(operations["deliverable"])
            self.assertTrue(operations["verify"])
        self.assertIn("asynchronous refunds"," ".join(output["outputs"][2]["packet"]["operations"]["tasks"]))
        self.assertIn("correct citations"," ".join(output["outputs"][6]["packet"]["operations"]["tasks"]))

    def test_missing_stale_release_and_critical_evidence(self):
        self.assertEqual(evaluate(self.app,[])[1]["status"],"BLOCKED")
        record=self.record("readiness")
        self.assertTrue(current(record,self.app))
        record["data"]["checked_at"]=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
        self.assertFalse(current(record,self.app))
        record["data"]["checked_at"]=now();record["data"]["release"]="wrong"
        self.assertFalse(current(record,self.app))
        for kind in {k for s in stages() for k in s["inputs"] if k!="manifest"}:self.record(kind)
        self.record("review",dict(external_id="r",release="test-build",locale="en-US",rating=1,theme="Broken checkout",severity="P0",confirmed=True))
        result=evaluate(self.app,self.store.records("test-app"))
        self.assertEqual(result[6]["status"],"BLOCKED")
        self.assertTrue(any("critical" in item for item in result[6]["missing"]))

    def test_new_failure_overrides_older_pass(self):
        self.record("readiness")
        self.record("readiness",dict(evidence_data("readiness"),result="FAIL",p0_count=1))
        result=evaluate(self.app,self.store.records("test-app"))
        self.assertEqual(result[1]["status"],"BLOCKED")
        self.assertIn("latest result",result[1]["missing"][0])

    def test_queue_idempotency_and_restart(self):
        body={"action":"pipeline","data":{"stage":0},"request_key":"same-key"}
        first=self.service.queue("test-app",body)
        self.assertEqual(first["id"],self.service.queue("test-app",body)["id"])
        with self.assertRaises(Invalid):self.service.queue("test-app",dict(body,data={"stage":1}))
        self.assertTrue(run_once(Store(self.store.path)))
        result=jobs(self.store,"test-app")[0]
        self.assertEqual(result["status"],"SUCCEEDED")
        self.assertEqual(len(result["result"]["outputs"]),12)
        self.assertFalse(run_once(self.store))
        self.assertEqual(len(jobs(self.store,"test-app")),1)

    def test_expired_lease_and_attempt_limit(self):
        self.service.queue("test-app",{"action":"pipeline","data":{"stage":1},"request_key":"lease"})
        job=claim(self.store)
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET lease=0 WHERE id=?",(job["id"],))
        self.assertTrue(run_once(self.store))
        self.assertEqual(jobs(self.store,"test-app")[0]["attempts"],2)
        second=self.service.queue("test-app",{"action":"pipeline","data":{"stage":1},"request_key":"exhausted"})
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET lease=0,status='RUNNING',attempts=3 WHERE id=?",(second["id"],))
        self.assertIsNone(claim(self.store))
        self.assertEqual(next(j for j in jobs(self.store,"test-app") if j["id"]==second["id"])["status"],"FAILED")

    def test_cancel_remains_cancelled_during_completion(self):
        job=self.service.queue("test-app",{"action":"pipeline","data":{"stage":0},"request_key":"cancel"})
        def during_process(store,job):
            self.service.cancel("test-app",job["id"])
            return {"would_have_finished":True}
        with patch("mission_control.worker.process",side_effect=during_process):run_once(self.store)
        self.assertEqual(jobs(self.store,"test-app")[0]["status"],"CANCELLED")
        with self.assertRaises(Invalid):self.service.cancel("sample-one",job["id"])

    def test_worker_error_visible_and_runner_lifecycle(self):
        self.service.queue("test-app",{"action":"pipeline","data":{"stage":0},"request_key":"error"})
        with patch("mission_control.worker.process",side_effect=RuntimeError("Synthetic recoverable failure")):run_once(self.store)
        self.assertEqual(jobs(self.store,"test-app")[0]["status"],"BLOCKED")
        self.assertIn("Synthetic",jobs(self.store,"test-app")[0]["result"]["error"])
        runner=Runner(self.store);runner.start();runner.stop();self.assertFalse(runner.thread.is_alive())

    def test_review_independence_changed_hash_expiry(self):
        record=self.record("distribution")
        prepared=self.service.prepare_review("test-app",{"record_id":record["id"]})
        review=self.service.approvals("test-app")[0]
        with self.assertRaises(Invalid):self.service.review("test-app",prepared["id"],{"hash":review["hash"]})
        checker=Service(self.store,"independent-checker")
        with self.assertRaises(Invalid):checker.review("test-app",prepared["id"],{"hash":"wrong"})
        result=checker.review("test-app",prepared["id"],{"hash":review["hash"]})
        self.assertEqual(result["status"],"REVIEW_RECORDED")
        self.assertEqual(result["external_execution"],"MANUAL_ONLY")
        with self.assertRaises(Invalid):checker.review("test-app",prepared["id"],{"hash":review["hash"]})
        fresh=self.service.prepare_review("test-app",{"record_id":record["id"]})
        self.store.save_record("test-app",dict(record,data=dict(record["data"],intent="changed")))
        freshrow=next(r for r in checker.approvals("test-app") if r["id"]==fresh["id"])
        with self.assertRaises(Invalid):checker.review("test-app",fresh["id"],{"hash":freshrow["hash"]})

    def test_review_expiry_and_manifest_change(self):
        record=self.record("distribution")
        checker=Service(self.store,"independent-checker")
        expired=self.service.prepare_review("test-app",{"record_id":record["id"]})
        row=self.service.approvals("test-app")[0]
        with connection(self.store.path) as db:
            db.execute("UPDATE approvals SET expires=? WHERE id=?",((datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),expired["id"]))
        with self.assertRaisesRegex(Invalid,"expired"):
            checker.review("test-app",expired["id"],{"hash":row["hash"]})
        fresh=self.service.prepare_review("test-app",{"record_id":record["id"]})
        row=next(r for r in checker.approvals("test-app") if r["id"]==fresh["id"])
        self.store.save_app("test-app",dict(self.app["data"],release="new-build"),self.app["version"])
        with self.assertRaisesRegex(Invalid,"setup changed"):
            checker.review("test-app",fresh["id"],{"hash":row["hash"]})

    def test_snapshot_integrity_restore_and_atomic_conflict(self):
        self.record("claim")
        snapshot=self.store.export("test-app")
        restored=Store(Path(self.tmp.name)/"restored.sqlite",seed=False)
        restored.restore(snapshot)
        self.assertEqual(len(restored.records("test-app")),1)
        with self.assertRaises(Invalid):restored.restore(snapshot)
        bad=copy.deepcopy(snapshot);bad["payload"]["records"][0]["app_id"]="sample-one";bad["sha256"]=digest(bad["payload"])
        other=Store(Path(self.tmp.name)/"other.sqlite",seed=False)
        with self.assertRaises(Invalid):other.restore(bad)
        self.assertEqual(other.apps(),[])
        bad=copy.deepcopy(snapshot);bad["sha256"]="incorrect"
        with self.assertRaises(Invalid):other.restore(bad)

    def test_upload_hash_scope_and_invalid_paths(self):
        raw=b"\x89PNG\r\n\x1a\n"+b"synthetic-not-an-authentic-capture"
        record=self.service.upload("test-app","proof.png",raw)
        self.assertFalse(record["data"]["authentic"])
        self.assertFalse(record["data"]["rights_cleared"])
        record["data"].update(device="synthetic",authentic=True,rights_cleared=True)
        self.service.evidence("test-app",record)
        with self.assertRaises(Invalid):self.service.upload("test-app","proof.svg",raw)
        record["data"]["file_id"]="../state.sqlite"
        with self.assertRaises(Invalid):self.service.evidence("test-app",record)

    def test_metrics_zero_immature_and_impossible_counts(self):
        data=evidence_data("cohort")
        metric=cohort_metrics(data)
        self.assertEqual(metric["paid_cac_minor"],100)
        self.assertEqual(metric["contribution_after_acquisition_minor"],3500)
        data.update(installs=0,paid=0,activated=0)
        self.assertIsNone(cohort_metrics(data)["paid_cac_minor"])
        data["mature"]=False;self.assertEqual(cohort_metrics(data)["status"],"INCONCLUSIVE")
        data.update(installs=1,paid=2)
        with self.assertRaises(Invalid):cohort_metrics(data)
        self.assertIsNone(ratio(0,0))
        self.assertEqual(retention_metrics(evidence_data("retention"))["rate"],0.4)
        with self.assertRaises(Invalid):retention_metrics({"eligible":1,"retained":2})

    def test_input_contracts_and_secret_rejection(self):
        for function,args in [(amount,(True,"amount")),(fraction,(float("nan"),"fraction")),(identifier,("../bad",)),(iso_time,("2026-10-11",)),(required,(None,"name")),(safe_data,({"access_token":"do-not-store"},))]:
            with self.subTest(function=function.__name__),self.assertRaises(Invalid):function(*args)
        self.assertEqual(canonical({"b":2,"a":1}),'{"a":1,"b":2}')
        self.assertEqual(len(uid()),36)
        self.assertEqual(fraction(0.5,"fraction"),0.5)
        with self.assertRaises(Invalid):validate_values({"mature":"yes"})
        with self.assertRaises(Invalid):validate_evidence("readiness",{},"test-app")
        with self.assertRaises(Invalid):self.service.queue("test-app",{"action":"pipeline","data":{"stage":True},"request_key":"bad"})

    def test_provider_scope_and_missing_credential(self):
        with self.assertRaises(Invalid):credential({"env_ref":"GROWTH_SAMPLE_ONE_TOKEN"},"test-app")
        binding={"provider":"app_store","env_ref":"GROWTH_TEST_APP_APP_STORE_TOKEN","store_app_id":"123","account_id":"123"}
        validate_binding(binding,"test-app")
        with patch.dict(os.environ,{},clear=True),self.assertRaises(Invalid):sync(binding,"test-app")
        with patch.dict(os.environ,{binding["env_ref"]:"synthetic"}),patch("mission_control.providers.read_json",return_value={"data":{"id":"123"}}) as request:
            result=sync(binding,"test-app")
            self.assertEqual(result["app_id"],"test-app")
            self.assertTrue(request.call_args[0][0].startswith("https://api.appstoreconnect.apple.com/"))
        with self.assertRaises(Invalid):NoRedirect().redirect_request(None,None,302,"",{},"https://evil.example")
        campaign=scope_payload({"data":[{"adamId":123},{"adamId":456}]},"apple_ads","123")
        self.assertEqual(campaign["data"],[{"adamId":123}])
        with self.assertRaises(Invalid):scope_payload({"data":{"id":"456"}},"app_store","123")

    def test_snapshot_restores_asset_bytes(self):
        record=self.service.upload("test-app","synthetic.png",b"\x89PNG\r\n\x1a\nfixture")
        snapshot=self.store.export("test-app")
        other=Store(Path(self.tmp.name)/"new-folder/backup.sqlite",seed=False)
        other.restore(snapshot)
        self.assertEqual((other.path.parent/"files/test-app"/record["data"]["file_id"]).read_bytes(),b"\x89PNG\r\n\x1a\nfixture")

    def test_restore_rejects_asset_mismatch_and_rolls_back_file_failure(self):
        record=self.service.upload("test-app","synthetic.png",b"\x89PNG\r\n\x1a\nfixture")
        snapshot=self.store.export("test-app")
        other=Store(Path(self.tmp.name)/"recovery/state.sqlite",seed=False)
        bad=copy.deepcopy(snapshot)
        bad["payload"]["records"][0]["data"]["sha256"]="a"*64
        badrecord=bad["payload"]["records"][0]
        badrecord["hash"]=digest({"kind":badrecord["kind"],"data":badrecord["data"],"source":badrecord["source"]})
        bad["sha256"]=digest(bad["payload"])
        with self.assertRaisesRegex(Invalid,"does not match"):
            other.restore(bad)
        self.assertEqual(other.apps(),[])
        with patch("pathlib.Path.open",side_effect=OSError("Synthetic disk full")),self.assertRaises(OSError):
            other.restore(snapshot)
        self.assertEqual(other.apps(),[])
        other.restore(snapshot)
        self.assertEqual(len(other.records("test-app")),1)

    def test_stage_evaluation_performance(self):
        start=time.perf_counter()
        for _ in range(100):self.assertEqual(len(evaluate(self.app,[])),12)
        self.assertLess(time.perf_counter()-start,10)
        self.assertEqual(len(self.service.workspace("test-app")["stages"]),12)
        self.assertEqual(self.service.bootstrap()["authorized_spend_minor"],0)


if __name__=="__main__":unittest.main()
