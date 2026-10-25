"""Real source/SQLite/role/holdout transitions; outcomes are explicit synthetic exports."""
from contextlib import contextmanager,ExitStack
import copy
import json
from pathlib import Path
import tempfile
import time
from datetime import datetime
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.creative_briefs import Briefs
from mission_control.outcome_links import Links,current_link,joined
from mission_control.outcome_learning import Learning,find,history
from mission_control.learning_contract import declare
from mission_control.experiments import Experiments
from mission_control.review_access import Access
from tests.test_creative_production import ready_production
from tests.test_creative_library import reference
from tests.test_ledger import cohort,event
from tests.test_verified_review import OWNER,CHECKER,STRANGER

APP="learning-test"
PREP="2026-10-01T00:00:00+00:00"
PROPOSE="2026-10-06T00:00:00+00:00"
RESERVE="2026-10-07T12:00:00+00:00"
FINAL="2026-10-11T01:00:00+00:00"


@contextmanager
def clock(stamp):
    with ExitStack() as stack:
        for module in ("creative_briefs","creative_analysis","creative_library","experiments","outcome_links","learning_contract","outcome_learning","ledger"):
            stack.enter_context(patch("mission_control."+module+".now",return_value=stamp))
        stack.enter_context(patch("tests.test_creative_production.now",return_value=stamp))
        for module in ("ledger", "subscription_review"):
            observed=stack.enter_context(patch("mission_control."+module+".datetime",wraps=datetime))
            observed.now.return_value=datetime.fromisoformat(stamp)
        yield


class LearningFixture:
    def __init__(self,store,app=APP):
        self.store=store;self.app=app;self.service=Service(store);self.links=Links(store);self.learning=Learning(store);self.experiments=Experiments(store)
        with clock(PREP),patch("tests.test_creative_production.reference",return_value=reference(captured_at=PREP,published_at="2026-09-01T00:00:00+00:00")):
            _,_,records,self.brief_data=ready_production(store,app)
            self.briefs={arm:Briefs(store).save(app,{"data":dict(self.brief_data,objective="Synthetic "+arm+" rehearsal")}) for arm in ("control","treatment")}
        self.asset=records["asset"]["id"]
        access=Access(store);access.bootstrap(app,OWNER,{"confirm_owner":True});access.save(app,OWNER,CHECKER,{"login":CHECKER["login"],"role":"CHECKER","status":"ACTIVE","version":None})
        self.train=self.create("train","2026-10-02","2026-10-03","2026-10-04","2026-10-05",PREP)

    def create(self,name,start,end,mature,analysis,registered):
        variants={};release=self.store.app(self.app)["data"]["release"]
        for arm in ("control","treatment"):
            identity=name+"-"+arm
            self.service.cohort(self.app,cohort(cohort_id=identity,release=release,starts_at=start+"T00:00:00+00:00",ends_at=end+"T00:00:00+00:00",matures_at=mature+"T00:00:00+00:00"))
            variants[arm]={"cohort_id":identity,"asset_id":self.asset}
        plan=dict(name="Synthetic "+name,hypothesis="A fictional clearer demonstration",owner="Synthetic operator",primary_metric="activation_rate",baseline_rate=.2,minimum_detectable_effect=.4,treatment_allocation=.5,
                  analysis_at=analysis+"T00:00:00+00:00",assignment_method="OBSERVATIONAL",assignment_source="Synthetic disjoint export",guardrails={"min_retention_rate":.5,"max_refund_fraction":.1,"min_contribution_minor":0,"max_acquisition_minor":50000},stop_rule="Stop on P0",rollback_plan="Use previous original design",**variants)
        with clock(registered):return self.experiments.create(self.app,plan)

    def current(self,e):return next(r for r in self.experiments.list(self.app) if r["id"]==e["id"])

    def observe(self,e,count=100,treatment=90,shared=False,reuse_train=False):
        d=e["data"];start=d["control"]["cohort"]["starts_at"];retained=d["control"]["cohort"]["ends_at"]
        with clock(start):self.experiments.act(self.app,e["id"],{"operation":"observe","version":e["version"],"source":"Synthetic supplied exposure receipt","observed_at":start})
        for arm in ("control","treatment"):
            cohort_id=d[arm]["cohort_id"];rows=[]
            for n in range(count):
                subject=("shared-" if shared else cohort_id+"-")+str(n)
                if reuse_train and arm=="control" and n==0:subject="train-control-0"
                for kind,stamp,amount in (("INSTALL",start,0),("PURCHASE",start,1000),("VALUE",retained,0)):
                    rows.append(event(cohort_id+kind+str(n),kind,occurred_at=stamp,amount_minor=amount,subject=subject))
                if n<(20 if arm=="control" else treatment):rows.append(event(cohort_id+"ACT"+str(n),"ACTIVATION",occurred_at=start,subject=subject))
            rows.extend([event(cohort_id+"-delivery","COST_DELIVERY",occurred_at=start,amount_minor=100),event(cohort_id+"-acquisition","COST_ACQUISITION",occurred_at=start,amount_minor=300)])
            self.service.events(self.app,{"cohort_id":cohort_id,"events":rows})

    def link(self,e,arm,brief=None):
        cohort_id=e["data"][arm]["cohort_id"]
        return self.links.save(self.app,{"version":None,"data":{"experiment_id":e["id"],"arm":arm,"brief_id":(brief or self.briefs[arm])["id"],"publication_url":"https://example.com/synthetic-"+cohort_id,"published_at":e["data"][arm]["cohort"]["starts_at"],"cost_events":[{"provider":"export","event_id":cohort_id+"-delivery"}]}})

    def complete(self,e,decision=True,stamp=FINAL):
        with clock(stamp):
            result=self.experiments.evaluate(self.app,e["id"])
            if decision:self.experiments.act(self.app,e["id"],{"operation":"decide","version":self.current(e)["version"],"assessment_hash":result["hash"],"decision":"NEXT_TEST","reason":"Synthetic descriptive next test"})
            for arm in ("control","treatment"):self.link(e,arm)
        return result

    def proposal(self):
        self.observe(self.train);self.complete(self.train)
        with clock(PROPOSE):return self.learning.propose(self.app,OWNER,{"name":"Synthetic question-first design","pattern":"Ask one specific question before showing the original demonstration.","training_experiment_id":self.train["id"],"minimum_holdout_difference":.1})

    def act(self,row,operation,user=OWNER,**extra):
        return self.learning.act(self.app,row["id"],user,operation,dict(version=row["version"],hash=row["hash"],**extra))

    def reserved(self):
        proposal=self.proposal();e=self.create("holdout","2026-10-08","2026-10-09","2026-10-10","2026-10-11","2026-10-07T00:00:00+00:00")
        with clock(RESERVE):row=self.act(proposal,"reserve",experiment_id=e["id"],control_brief_id=self.briefs["control"]["id"],treatment_brief_id=self.briefs["treatment"]["id"],confirm_pattern_test=True)
        return row,e

    def ready(self,treatment=90):
        row,e=self.reserved();self.observe(e,treatment=treatment);self.complete(e,False)
        with clock(FINAL):row=self.act(row,"evaluate")
        return row,e


class OutcomeLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"source/state.sqlite");self.f=LearningFixture(self.store)

    def tearDown(self):self.tmp.cleanup()

    def test_exact_links_and_costs_are_included_once(self):
        self.f.observe(self.f.train);self.f.complete(self.f.train)
        rows=self.f.links.list(APP);self.assertEqual(len(rows),2)
        self.assertTrue(all(r["availability"]=="CURRENT" and r["data"]["production_cost_minor"]==100 for r in rows))
        self.assertEqual(rows[0]["data"]["cost_treatment"],"ALREADY_INCLUDED_IN_DELIVERY_LEDGER")
        bad=copy.deepcopy(rows[0]["data"]["request"]);bad["cost_events"]*=2
        with self.assertRaises(Invalid):self.f.links.save(APP,{"version":1,"data":bad})
        bad["cost_events"]=[]
        with self.assertRaises(Invalid):self.f.links.save(APP,{"version":1,"data":bad})
        with self.assertRaises(Invalid):self.f.links.save("sample-two",{"version":None,"data":rows[0]["data"]["request"]})

    def test_holdout_independent_adoption_explicit_use_and_rollback(self):
        row,e=self.f.ready();self.assertEqual(row["state"],"READY")
        with clock(FINAL):
            with self.assertRaises(Invalid):self.f.act(row,"approve",confirm_local_guidance=True)
            with self.assertRaises(PermissionError):self.f.act(row,"approve",STRANGER,confirm_local_guidance=True)
            approved=self.f.act(row,"approve",CHECKER,confirm_local_guidance=True)
            with self.assertRaises(Invalid):self.f.act(row,"activate",confirm_activate=True)
            active=self.f.act(approved,"activate",confirm_activate=True)
            result=self.f.learning.use(APP,active["id"],OWNER,{"version":active["version"],"hash":active["hash"],"data":self.f.brief_data})
            self.assertIn("Creative method to test:",result["brief"]["data"]["definition"]["objective"])
            self.assertEqual(result["receipt"]["evaluation_hash"],active["data"]["evaluation_hash"])
            view=self.f.learning.list(APP);self.assertTrue(view["programs"][0]["active"]);self.assertEqual(len(view["uses"]),1)
            rolled=self.f.act(active,"rollback",confirm_rollback=True,reason="Synthetic actual local rollback")
            self.assertEqual(rolled["state"],"ROLLED_BACK");self.assertIsNone(self.f.learning.list(APP)["active_id"])
            with self.assertRaises(Invalid):self.f.learning.use(APP,rolled["id"],OWNER,{"version":rolled["version"],"hash":rolled["hash"],"data":self.f.brief_data})

    def test_holdout_reuse_and_observed_future_test_reject(self):
        row,e=self.f.reserved()
        self.f.observe(e)
        with clock(RESERVE),self.assertRaises(Invalid):self.f.act(row,"reserve",experiment_id=e["id"],control_brief_id=self.f.briefs["control"]["id"],treatment_brief_id=self.f.briefs["treatment"]["id"],confirm_pattern_test=True)
        with connection(self.store.path) as db:
            from mission_control.learning_contract import reserve_role
            with self.assertRaises(Invalid):reserve_role(db,APP,e["id"],"TRAIN","other")

    def test_weak_outcomes_never_become_winners(self):
        row,e=self.f.ready(treatment=20);self.assertEqual(row["state"],"REJECTED")
        self.assertTrue(row["data"]["evaluation"]["issues"])
        with clock(FINAL),self.assertRaises(Invalid):self.f.act(row,"approve",CHECKER,confirm_local_guidance=True)
        for value in (0,1,True,float("nan"),float("inf")):
            with self.assertRaises(Invalid):declare({"name":"x","pattern":"x","training_experiment_id":"x","minimum_holdout_difference":value})

    def test_late_refund_role_revocation_and_source_truth(self):
        row,e=self.f.ready()
        with clock(FINAL):
            approved=self.f.act(row,"approve",CHECKER,confirm_local_guidance=True);active=self.f.act(approved,"activate",confirm_activate=True)
            cohort_id=e["data"]["treatment"]["cohort_id"]
            self.f.service.events(APP,{"cohort_id":cohort_id,"events":[event("late-refund","REFUND",day="2026-10-11",amount=1000,related=cohort_id+"PURCHASE0")]})
            from mission_control.learning_contract import assessment
            with connection(self.store.path) as db,self.assertRaisesRegex(Invalid,"Outcomes changed"):assessment(db,self.store,APP,e["id"])
            self.assertEqual(self.f.learning.list(APP)["programs"][0]["availability"],"UNAVAILABLE")
            with self.assertRaises(Invalid):self.f.learning.use(APP,active["id"],OWNER,{"version":active["version"],"hash":active["hash"],"data":self.f.brief_data})
            self.f.act(active,"rollback",confirm_rollback=True,reason="Late refund source changed")
        with connection(self.store.path) as db:
            records=db.execute("SELECT count(*) FROM learning_events WHERE app_id=?",(APP,)).fetchone()[0]
        self.assertEqual(records,6)

    def test_role_regrant_does_not_restore_old_approval(self):
        row,_=self.f.ready();access=Access(self.store)
        with clock(FINAL):
            approved=self.f.act(row,"approve",CHECKER,confirm_local_guidance=True)
            access.save(APP,OWNER,CHECKER,{"login":CHECKER["login"],"role":"CHECKER","status":"REVOKED","version":1})
            with self.assertRaises(PermissionError):self.f.act(approved,"activate",confirm_activate=True)
            access.save(APP,OWNER,CHECKER,{"login":CHECKER["login"],"role":"CHECKER","status":"ACTIVE","version":2})
            with self.assertRaises(Invalid):self.f.act(approved,"activate",confirm_activate=True)
            self.assertEqual(self.f.learning.list(APP)["programs"][0]["availability"],"UNAVAILABLE")

    def test_training_subject_in_holdout_and_immature_data_reject(self):
        row,e=self.f.reserved()
        with clock(RESERVE):
            rejected=self.f.act(row,"evaluate")
            self.assertEqual(rejected["state"],"REJECTED")
            self.assertIn("fixed analysis",rejected["data"]["evaluation"]["issues"][0])
        self.f.observe(e,reuse_train=True);self.f.complete(e,False)
        with clock(FINAL):
            rejected=self.f.act(rejected,"evaluate")
            self.assertEqual(rejected["state"],"REJECTED")
            self.assertIn("share observed install",rejected["data"]["evaluation"]["issues"][0])
            with self.assertRaises(Invalid):self.f.act(rejected,"approve",CHECKER,confirm_local_guidance=True)

    def test_preobserved_cohort_cannot_be_reserved_and_manifest_changes_block(self):
        row=self.f.proposal()
        e=self.f.create("preseen","2026-10-08","2026-10-09","2026-10-10","2026-10-11","2026-10-07T00:00:00+00:00")
        self.f.service.events(APP,{"cohort_id":"preseen-control","events":[event("early-observation","INSTALL",occurred_at="2026-10-08T00:00:00+00:00",subject="synthetic")]})
        with clock(RESERVE),self.assertRaisesRegex(Invalid,"already contain"):
            self.f.act(row,"reserve",experiment_id=e["id"],control_brief_id=self.f.briefs["control"]["id"],treatment_brief_id=self.f.briefs["treatment"]["id"],confirm_pattern_test=True)
        manifest=self.store.app(APP)
        self.store.save_app(APP,dict(manifest["data"],name="Changed manifest"),manifest["version"])
        with clock(RESERVE):self.assertEqual(self.f.learning.list(APP)["programs"][0]["availability"],"UNAVAILABLE")

    def test_exact_actions_corruption_and_cross_app_never_fall_back(self):
        row,_=self.f.ready()
        with clock(FINAL):
            for body in ({"version":True,"hash":row["hash"]},{"version":row["version"],"hash":"forged"},{"version":row["version"],"hash":row["hash"],"extra":True}):
                with self.assertRaises(Invalid):self.f.learning.act(APP,row["id"],OWNER,"evaluate",body)
            with self.assertRaises(Invalid):self.f.learning.act("sample-two",row["id"],OWNER,"evaluate",{"version":row["version"],"hash":row["hash"]})
            with self.assertRaises(Invalid):self.f.act(row,"unknown")
            with self.assertRaises(Invalid):self.f.act(row,"approve",CHECKER,confirm_local_guidance="true")
        with connection(self.store.path) as db:db.execute("DELETE FROM learning_events WHERE app_id=? AND version=2",(APP,))
        with self.assertRaisesRegex(Invalid,"sequence"):self.f.learning.list(APP)

    def test_source_asset_and_reserved_brief_changes_are_not_green(self):
        row,e=self.f.reserved();self.f.observe(e);self.f.complete(e,False)
        with clock(FINAL):
            old=self.f.briefs["treatment"]
            Briefs(self.store).save(APP,{"id":old["id"],"version":1,"data":dict(self.f.brief_data,objective="A changed design after reservation")})
            result=self.f.act(row,"evaluate")
            self.assertEqual(result["state"],"REJECTED")
            self.assertIn("source changed",result["data"]["evaluation"]["issues"][0].lower())
            request=next(r for r in self.f.links.list(APP) if r["experiment_id"]==e["id"] and r["arm"]=="treatment")
            self.f.links.save(APP,{"version":1,"data":request["data"]["request"]})
            result=self.f.act(result,"evaluate")
            self.assertEqual(result["state"],"REJECTED")

    def test_actual_rollback_restores_previous_eligible_method(self):
        first,_=self.f.ready()
        with clock(FINAL):
            first=self.f.act(first,"approve",CHECKER,confirm_local_guidance=True)
            first=self.f.act(first,"activate",confirm_activate=True)
            definition=dict(first["data"]["definition"],name="Second independently tested method")
            second=self.f.learning.propose(APP,OWNER,definition)
        future=self.f.create("second","2026-10-12","2026-10-13","2026-10-14","2026-10-15","2026-10-11T02:00:00+00:00")
        with clock("2026-10-11T03:00:00+00:00"):
            second=self.f.act(second,"reserve",experiment_id=future["id"],control_brief_id=self.f.briefs["control"]["id"],treatment_brief_id=self.f.briefs["treatment"]["id"],confirm_pattern_test=True)
        with clock("2026-10-15T00:00:00+00:00"):self.f.observe(future)
        self.f.complete(future,False,stamp="2026-10-15T00:00:00+00:00")
        with clock("2026-10-15T00:00:00+00:00"):
            second=self.f.act(second,"evaluate");self.assertEqual(second["state"],"READY")
            second=self.f.act(second,"approve",CHECKER,confirm_local_guidance=True)
            second=self.f.act(second,"activate",confirm_activate=True)
            states={r["id"]:r["state"] for r in self.f.learning.list(APP)["programs"]}
            self.assertEqual(states[first["id"]],"SUPERSEDED")
            rolled=self.f.act(second,"rollback",confirm_rollback=True,reason="Restore previous locally approved method")
            self.assertEqual(rolled["data"]["rollback"]["restored_id"],first["id"])
            self.assertEqual(self.f.learning.list(APP)["active_id"],first["id"])

    def test_twenty_proposals_reuse_current_report_context(self):
        first=self.f.proposal()
        with clock(FINAL):
            for n in range(19):self.f.learning.propose(APP,OWNER,dict(first["data"]["definition"],name="Synthetic method "+str(n)))
            from mission_control import learning_contract
            started=time.perf_counter()
            with patch("mission_control.learning_contract.evidence_reports",wraps=learning_contract.evidence_reports) as reports:
                rows=self.f.learning.list(APP)
                self.assertEqual(reports.call_count,1)
            elapsed=time.perf_counter()-started
            self.assertEqual(len(rows["programs"]),20);self.assertLess(elapsed,10)

    def test_source_helpers_preserve_exact_cost_design_and_role_boundaries(self):
        from mission_control.outcome_links import bind_link,bound_brief,cost_identity,validate_link,decoded,link_capacity
        from mission_control.learning_contract import source_current,overlap_subjects,eligible
        from mission_control.outcome_learning import transition,available,check_receipt,history_capacity
        row,e=self.f.ready()
        with clock(FINAL),connection(self.store.path) as db:
            self.assertEqual(source_current(db,self.store,row)["assessment"]["status"],"EVALUATED")
            self.assertEqual(overlap_subjects(db,APP,self.f.train,e),0)
            self.assertEqual(eligible(db,self.store,row)["outcome"],"READY")
            self.assertEqual(available(db,self.store,row),[])
            link=current_link(db,APP,e["id"],"control")
            self.assertEqual(validate_link(db,self.store,APP,e,link),link)
            request=link["data"]["request"]
            self.assertEqual(bind_link(db,self.store,APP,request),link["data"])
            with self.assertRaises(Invalid):bind_link(db,self.store,APP,dict(request,arm="foreign"))
            with self.assertRaises(Invalid):cost_identity({"provider":"export"})
            with self.assertRaises(Invalid):bound_brief(db,self.store,"sample-two",request["brief_id"],e["data"]["control"])
            with self.assertRaises(Invalid):decoded({"data":"{}","hash":"forged"})
            with self.assertRaises(Invalid):transition(db,row,"UNKNOWN",row["data"],"unknown",OWNER["principal"])
            events=history(db,row);bad=copy.deepcopy(events[0]);bad["data"]["previous_hash"]="forged"
            with self.assertRaises(Invalid):check_receipt(bad,[],row)
            # Capacity is shared across declarations and transitions, not just list truncation.
            db.executemany("INSERT INTO learning_events VALUES(?,?,?,?,?,?)",[(APP,"synthetic-capacity",n,"{}",digest({}),FINAL) for n in range(1,5001)])
            with self.assertRaises(Invalid):history_capacity(db,APP)
            db.execute("DELETE FROM learning_events WHERE learning_id='synthetic-capacity'")
            link_capacity(db,APP,None)



