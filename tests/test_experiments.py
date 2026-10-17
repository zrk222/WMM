"""Scoped immutable experiments with real SQLite/files and explicit synthetic observations."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.experiments import (Experiments,definition_data,bind_variant,bind_definition,decoded,lookup,evidence_reports,
                                       quality_findings,asset_intact,snapshot_data,validate_frozen,validate_frozen_variant,validate_frozen_windows)
from mission_control.experiment_analysis import sample_plan,wilson,guardrail_data,sample_diagnostics,guardrail_findings
from mission_control.store import Store
from mission_control.service import Service
from tests.test_ledger import cohort,event

PNG=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jmrkAAAAASUVORK5CYII=")
REGISTER="2026-08-30T00:00:00+00:00"
EXPOSE="2026-09-02T00:00:00+00:00"
ANALYZE="2026-10-02T00:00:00+00:00"
LATER="2026-10-07T00:00:00+00:00"


def prepared(store,app_id="sample-one",release="build-1"):
    service=Service(store);app=store.app(app_id)
    store.save_app(app_id,dict(app["data"],release=release,currency="USD",locale="en-US"),app["version"])
    variants={}
    for arm in ("control","treatment"):
        service.cohort(app_id,cohort(cohort_id="experiment-"+arm,release=release))
        record=service.upload(app_id,"synthetic-"+arm+".png",PNG)
        record=service.evidence(app_id,dict(record,data=dict(record["data"],authentic=True,rights_cleared=True,device="Synthetic test image"),source="Synthetic fixture, not an app screenshot"))
        variants[arm]={"cohort_id":"experiment-"+arm,"asset_id":record["id"]}
    return dict(name="Synthetic bounded test",hypothesis="A clearer rehearsal may improve activation",owner="Synthetic operator",primary_metric="activation_rate",baseline_rate=.1,
                minimum_detectable_effect=.5,treatment_allocation=.5,analysis_at=ANALYZE,assignment_method="OBSERVATIONAL",assignment_source="Synthetic disjoint assignment export",
                guardrails={"min_retention_rate":.5,"max_refund_fraction":.1,"min_contribution_minor":0,"max_acquisition_minor":50000},stop_rule="Stop for unresolved P0",rollback_plan="Return to original synthetic creative",**variants)


def observations(arm,count=20,activations=10,shared=False):
    rows=[]
    for n in range(count):
        subject=("shared" if shared else arm)+str(n)
        for kind,day,amount in (("INSTALL","2026-09-02",0),("PURCHASE","2026-09-03",1000),("VALUE","2026-09-20",0)):
            rows.append(event(arm+kind+str(n),kind,day,amount,subject=subject))
        if n<activations:rows.append(event(arm+"active"+str(n),"ACTIVATION",subject=subject))
    rows.extend([event(arm+"cost-a","COST_ACQUISITION",amount=300),event(arm+"cost-d","COST_DELIVERY",amount=100)])
    return rows


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"source/state.sqlite")
        self.service=Service(self.store);self.experiments=Experiments(self.store)
        self.plan=prepared(self.store)

    def tearDown(self):self.tmp.cleanup()

    def create(self):
        with patch("mission_control.experiments.now",return_value=REGISTER):return self.experiments.create("sample-one",self.plan)

    def current(self,e):return next(r for r in self.experiments.list("sample-one") if r["id"]==e["id"])

    def observe(self,e):
        with patch("mission_control.experiments.now",return_value=EXPOSE):
            return self.experiments.act("sample-one",e["id"],{"operation":"observe","version":e["version"],"source":"Synthetic exposure receipt","observed_at":EXPOSE})

    def ingest(self,**options):
        for arm in ("control","treatment"):
            self.service.events("sample-one",{"cohort_id":"experiment-"+arm,"events":observations(arm,activations=10 if arm=="control" else 16,**options)})

    def evaluated(self):
        e=self.create();self.observe(e);self.ingest()
        with patch("mission_control.experiments.now",return_value=ANALYZE):result=self.experiments.evaluate("sample-one",e["id"])
        return self.current(e),result

    def decision(self,e,result,decision="NEXT_TEST"):
        body={"operation":"decide","version":e["version"],"assessment_hash":result["hash"],"decision":decision,"reason":"Synthetic reviewed descriptive comparison"}
        with patch("mission_control.experiments.now",return_value=ANALYZE):return self.experiments.act("sample-one",e["id"],body)

    def test_planning_math_and_invalid_inputs(self):
        self.assertEqual(sample_plan(.2,.1,.5)["control"],295)
        low,high=wilson(0,10);self.assertEqual(low,0);self.assertAlmostEqual(high,.2775401687666166)
        for args in ((0,.1,.5),(.8,.3,.5),(.1,.1,0),(.1,.1,True),(.1,float("nan"),.5)):
            with self.subTest(args=args),self.assertRaises(Invalid):sample_plan(*args)
        bad=copy.deepcopy(self.plan);bad["guardrails"]["min_contribution_minor"]=True
        with patch("mission_control.experiments.now",return_value=REGISTER),self.assertRaises(Invalid):self.experiments.create("sample-one",bad)

    def test_definition_and_source_boundary_validators(self):
        normalized=definition_data(self.plan);self.assertEqual(normalized["sample_plan"]["control"],15)
        with connection(self.store.path) as db:
            variant=bind_variant(db,"sample-one",self.plan["control"])
            bound=bind_definition(db,"sample-one",self.plan,REGISTER)
            self.assertEqual(bound["control"]["cohort_hash"],variant["cohort_hash"])
            self.assertEqual(quality_findings(db,"sample-one",bound,self.store.path.parent/"files/sample-one"),[])
            with self.assertRaises(Invalid):bind_variant(db,"sample-two",self.plan["control"])
        record=next(r for r in self.store.records("sample-one") if r["id"]==variant["asset_id"])
        self.assertTrue(asset_intact(self.store.path.parent/"files/sample-one",record["data"]))
        self.assertFalse(asset_intact(self.store.path.parent/"files/sample-one",dict(record["data"],file_id="../../other.png")))
        e=self.create();self.observe(e);self.ingest()
        with connection(self.store.path) as db:
            self.assertEqual(lookup(db,"sample-one",e["id"])["version"],2)
            self.assertEqual(decoded(db.execute("SELECT * FROM experiments WHERE id=?",(e["id"],)).fetchone())["hash"],e["hash"])
            reports,overlap=evidence_reports(db,"sample-one",e["data"],ANALYZE)
        self.assertEqual(overlap,0);self.assertEqual(reports["treatment"]["activated"],16)

    def test_diagnostics_financial_denominators_and_declared_limits(self):
        e,result=self.evaluated();reports=result["result"]["reports"]
        checks=sample_diagnostics(reports,e["data"]["sample_plan"],.5)
        self.assertEqual(checks["issues"],[])
        self.assertEqual(guardrail_findings(reports,guardrail_data(self.plan["guardrails"])),[])
        missing=copy.deepcopy(reports);missing["control"]["net_proceeds_minor"]=0
        self.assertTrue(guardrail_findings(missing,self.plan["guardrails"]))
        limited=dict(self.plan["guardrails"],max_acquisition_minor=0)
        self.assertTrue(guardrail_findings(reports,limited))
        for bad in ({},dict(limited,max_refund_fraction=1.01),dict(limited,max_acquisition_minor=-1)):
            with self.assertRaises(Invalid):guardrail_data(bad)

    def test_frozen_snapshot_schema_and_window_validators(self):
        e=self.create();rows=self.store.export("sample-one")["payload"]["experiments"]
        self.assertEqual(snapshot_data(rows),rows)
        with connection(self.store.path) as db:
            validate_frozen(db,"sample-one",rows[0]);validate_frozen_variant(db,"sample-one",e["data"]["control"])
            with self.assertRaises(Invalid):validate_frozen_variant(db,"sample-two",e["data"]["control"])
            bad=copy.deepcopy(rows[0]);bad["data"]["control"]["cohort_hash"]="0"*64
            with self.assertRaises(Invalid):validate_frozen(db,"sample-one",bad)
        validate_frozen_windows(rows[0]);bad=copy.deepcopy(rows[0]);bad["created"]=EXPOSE
        with self.assertRaises(Invalid):validate_frozen_windows(bad)
        for bad in (None,{},[{}],rows*1001):
            with self.assertRaises(Invalid):snapshot_data(bad)

    def test_preregistration_and_scope(self):
        e=self.create();self.assertEqual(e["state"],"PLANNED");self.assertEqual(e["hash"],digest(e["data"]))
        with self.assertRaisesRegex(Invalid,"Pre-register"):self.experiments.create("sample-one",self.plan)
        with patch("mission_control.experiments.now",return_value=REGISTER),self.assertRaises(Invalid):self.experiments.create("sample-two",self.plan)
        for operation in ("observe","evaluate"):
            with self.assertRaises(Invalid):
                if operation=="evaluate":self.experiments.evaluate("sample-two",e["id"])
                else:self.experiments.act("sample-two",e["id"],{"operation":"cancel","version":1,"reason":"wrong app"})
        self.assertEqual(self.experiments.list("sample-two"),[])

    def test_current_source_checks_and_comparable_arms(self):
        bad=copy.deepcopy(self.plan);bad["treatment"]=bad["control"]
        with patch("mission_control.experiments.now",return_value=REGISTER),self.assertRaises(Invalid):self.experiments.create("sample-one",bad)
        asset=next(r for r in self.store.records("sample-one") if r["id"]==self.plan["control"]["asset_id"])
        path=self.store.path.parent/"files/sample-one"/asset["data"]["file_id"]
        original=path.read_bytes();path.write_bytes(b"changed")
        with patch("mission_control.experiments.now",return_value=REGISTER),self.assertRaisesRegex(Invalid,"file"):self.experiments.create("sample-one",self.plan)
        path.write_bytes(original);e=self.create();path.write_bytes(b"changed")
        with patch("mission_control.experiments.now",return_value=EXPOSE),self.assertRaisesRegex(Invalid,"file"):self.observe(e)

    def test_exposure_timing_versions_and_idempotence(self):
        e=self.create()
        with self.assertRaises(Invalid):self.experiments.evaluate("sample-one",e["id"])
        for timestamp in (REGISTER,"2999-01-01T00:00:00+00:00"):
            with patch("mission_control.experiments.now",return_value=EXPOSE),self.assertRaises(Invalid):
                self.experiments.act("sample-one",e["id"],dict(operation="observe",version=1,source="Synthetic",observed_at=timestamp))
        self.observe(e);self.assertEqual(self.observe(e)["status"],"ALREADY_RECORDED")
        with self.assertRaisesRegex(Invalid,"changed"):self.experiments.act("sample-one",e["id"],dict(operation="cancel",version=1,reason="stale"))
        with patch("mission_control.experiments.now",return_value=EXPOSE):
            result=self.experiments.evaluate("sample-one",e["id"])
        self.assertEqual(result["status"],"AWAITING_ANALYSIS");self.assertEqual(self.current(e)["assessments"],[])

    def test_mature_comparison_decision_and_rollback(self):
        e,result=self.evaluated();self.assertEqual(result["result"]["status"],"EVALUATED")
        effect=result["result"]["effect"];self.assertAlmostEqual(effect["difference"],.3)
        self.assertLess(effect["interval"][0],.3);self.assertGreater(effect["interval"][1],.3)
        self.decision(e,result);current=self.current(e);self.assertEqual(current["decision_status"],"CURRENT")
        with patch("mission_control.experiments.now",return_value=ANALYZE):
            self.assertFalse(self.experiments.evaluate("sample-one",e["id"])["new_assessment"])
            result=self.experiments.act("sample-one",e["id"],dict(operation="rollback",version=current["version"],target="original",source="Synthetic receipt",reason="Operator review"))
        self.assertEqual(result["external_execution"],"NOT_RUN")
        self.assertEqual(self.current(e)["state"],"DECIDED")

    def test_missing_sample_and_guardrails_prevent_next_test(self):
        e=self.create();self.observe(e);self.ingest(count=2)
        with patch("mission_control.experiments.now",return_value=ANALYZE):result=self.experiments.evaluate("sample-one",e["id"])
        self.assertEqual(result["result"]["status"],"INCONCLUSIVE");self.assertIsNone(result["result"]["effect"])
        with self.assertRaisesRegex(Invalid,"missing evidence"):self.decision(self.current(e),result)
        self.decision(self.current(e),result,"COLLECT")

    def test_contamination_and_critical_review_block(self):
        e=self.create();self.observe(e);self.ingest(shared=True)
        with patch("mission_control.experiments.now",return_value=ANALYZE):result=self.experiments.evaluate("sample-one",e["id"])
        self.assertEqual(result["result"]["status"],"BLOCKED");self.assertIsNone(result["result"]["effect"])
        self.assertNotIn("shared0",json.dumps(result))
        self.store.save_record("sample-one",dict(kind="review",title="Synthetic P0",source="Synthetic QA",data={"severity":"P0","confirmed":True}))
        with patch("mission_control.experiments.now",return_value=LATER):result=self.experiments.evaluate("sample-one",e["id"])
        self.assertIn("Confirmed critical product finding requires repair",result["result"]["issues"])

    def test_allocation_mismatch_and_financial_guardrail(self):
        e=self.create();self.observe(e)
        for arm,count in (("control",20),("treatment",80)):
            self.service.events("sample-one",{"cohort_id":"experiment-"+arm,"events":observations(arm,count=count)})
        self.service.events("sample-one",{"cohort_id":"experiment-control","events":[event("refund","REFUND","2026-10-03",1000,"controlPURCHASE0")]})
        self.service.events("sample-one",{"cohort_id":"experiment-control","events":[event("refund"+str(i),"REFUND","2026-10-03",1000,"controlPURCHASE"+str(i)) for i in (1,2)]})
        with patch("mission_control.experiments.now",return_value=LATER):result=self.experiments.evaluate("sample-one",e["id"])
        self.assertTrue(any("ratio mismatch" in i for i in result["result"]["issues"]))
        self.assertTrue(result["result"]["guardrail_findings"])
        self.assertIsNone(result["result"]["effect"])

    def test_late_finance_restates_but_late_outcomes_do_not_move_fixed_window(self):
        e,result=self.evaluated();self.decision(e,result)
        self.service.events("sample-one",{"cohort_id":"experiment-control","events":[event("late-active","ACTIVATION","2026-10-05",subject="control19"),event("late-refund","REFUND","2026-10-05",1000,"controlPURCHASE0")]})
        with patch("mission_control.experiments.now",return_value=LATER):late=self.experiments.evaluate("sample-one",e["id"])
        self.assertEqual(late["result"]["reports"]["control"]["activated"],10)
        self.assertEqual(late["result"]["reports"]["control"]["refunds_minor"],1000)
        self.assertNotEqual(late["hash"],result["hash"])
        self.assertEqual(self.current(e)["decision_status"],"STALE_ASSESSMENT")
        with self.assertRaisesRegex(Invalid,"changed"):self.decision(self.current(e),result)

    def test_changed_asset_repair_restores_evaluation_without_losing_history(self):
        e,result=self.evaluated();asset=next(r for r in self.store.records("sample-one") if r["id"]==self.plan["control"]["asset_id"])
        path=self.store.path.parent/"files/sample-one"/asset["data"]["file_id"];original=path.read_bytes()
        path.write_bytes(b"changed")
        with patch("mission_control.experiments.now",return_value=LATER):blocked=self.experiments.evaluate("sample-one",e["id"])
        self.assertEqual(blocked["result"]["status"],"BLOCKED")
        path.write_bytes(original)
        with patch("mission_control.experiments.now",return_value=LATER):repaired=self.experiments.evaluate("sample-one",e["id"])
        self.assertEqual(repaired["hash"],result["hash"]);self.assertTrue(repaired["new_assessment"])
        self.assertEqual([a["data"]["status"] for a in self.current(e)["assessments"]],["EVALUATED","BLOCKED","EVALUATED"])

    def test_cancel_terminal_and_snapshot_restore(self):
        e,result=self.evaluated();self.decision(e,result)
        with patch("mission_control.experiments.now",return_value=LATER):self.experiments.act("sample-one",e["id"],dict(operation="cancel",version=self.current(e)["version"],reason="Done collecting"))
        with self.assertRaises(Invalid):self.experiments.evaluate("sample-one",e["id"])
        exported=self.store.export("sample-one");target=Store(Path(self.tmp.name)/"restored/state.sqlite",seed=False)
        target.restore(exported)
        self.assertEqual(Experiments(target).list("sample-one"),self.experiments.list("sample-one"))
        legacy=copy.deepcopy(exported);legacy["payload"].pop("experiments");legacy["sha256"]=digest(legacy["payload"])
        old=Store(Path(self.tmp.name)/"legacy/state.sqlite",seed=False);old.restore(legacy);self.assertEqual(Experiments(old).list("sample-one"),[])

    def test_snapshot_tamper_atomic_rollback_and_history_replay(self):
        e,result=self.evaluated();self.decision(e,result);exported=self.store.export("sample-one")
        for mutation in ("scope","hash","version","state","assessment","decision"):
            bad=copy.deepcopy(exported);row=bad["payload"]["experiments"][0]
            if mutation=="scope":row["app_id"]="sample-two"
            if mutation=="hash":row["hash"]="0"*64
            if mutation=="version":row["version"]+=1
            if mutation=="state":row["state"]="CANCELLED"
            if mutation=="assessment":row["assessments"][0]["data"]["effect"]["difference"]=.4
            if mutation=="decision":
                row["actions"][-1]["data"]["assessment_hash"]="0"*64;row["actions"][-1]["hash"]=digest(row["actions"][-1]["data"])
            bad["sha256"]=digest(bad["payload"])
            target=Store(Path(self.tmp.name)/mutation/"state.sqlite",seed=False)
            with self.subTest(mutation=mutation),self.assertRaises(Invalid):target.restore(bad)
            self.assertEqual(target.apps(),[])
            self.assertFalse(list((target.path.parent/"files").rglob("*.png")))


if __name__=="__main__":unittest.main()
