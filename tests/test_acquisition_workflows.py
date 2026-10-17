"""Real isolated persistence, fixed denominators, source drift and hostile restore tests."""
import copy
from pathlib import Path
import tempfile
import time
import unittest
from mission_control.common import Invalid,digest,now
from mission_control.store import Store
from mission_control.service import Service
from mission_control.db import connection
from mission_control.acquisition_contract import exact,whole,intent_definition,bind_intent,bind_brief,intent_status,queries_data,panel_definition,observation_definition,answer_outcomes,failed_outcomes
from mission_control.acquisition_workflows import Acquisition,TABLES,slot,panel_current,require_panel,partition_counts,calculate,observation_rows,worksheet_rows
from mission_control.acquisition_portable import export_acquisition,historical,validate_intent,validate_records,validate_panel,validate_observation,validate_report,restore_acquisition,validate_intent_state,validate_intent_brief,validate_record,validate_record_locale,report_observations,restore_rows
from mission_control.creative_library import Library
from mission_control.creative_briefs import Briefs
from tests.test_creative_production import ready_production

APP="acquisition-test"


def ready_acquisition(store):
    """Synthetic product evidence only; no real research or provider outcomes."""
    source,analysis,records,_=ready_production(store,APP)
    data=dict(owner="Synthetic researcher",problem="Rehearse a fictional difficult conversation",asa_seed="conversation rehearsal",aeo_question="How can I rehearse a difficult conversation?",territory="US",native_reviewer="Synthetic English reviewer",analysis_id=analysis["id"],analysis_hash=analysis["hash"],claim_id=records["claim"]["id"],readiness_id=records["readiness"]["id"],route_id=records["route"]["id"],store_id=records["store"]["id"],brief_id=None,page_url="https://example.com/rehearsal")
    return data,records


def panel_data(intent,**changes):
    return dict(dict(intent_id=intent["id"],intent_hash=intent["hash"],owner="Synthetic researcher",engine="Synthetic answer engine",surface="API",search_mode="SEARCH_ON",model="NOT_EXPOSED",account_context="Synthetic fixture account",geography="US synthetic session",repetitions=2,rubric="Inspect whether the exact source supports the demonstrated claim; private data excluded",queries=[dict(id="problem",text="How do I rehearse a difficult conversation?",partition="CALIBRATION"),dict(id="comparison",text="How do rehearsal tools compare?",partition="HOLDOUT")]),**changes)


def answer(panel,query="problem",repetition=1,**changes):
    return dict(dict(panel_id=panel["id"],panel_hash=panel["hash"],query_id=query,repetition=repetition,observed_at=now(),status="OK",raw_response="Synthetic answer names Synthetic QA App and links its fictional rehearsal demonstration.",source_ref="Synthetic captured-answer receipt",reviewer="Synthetic reviewer",mention=True,citation_url="https://example.com/rehearsal",correct_citation=True,misinformation=False,review_note="Synthetic source supports the exact fictional demonstration claim"),**changes)


class AcquisitionTests(unittest.TestCase):
    def test_source_capture_refresh_and_optional_creative_scope(self):
        asset=next(r for r in self.store.records(APP) if r["kind"]=="asset")
        brief_definition=dict(analysis_id=self.data["analysis_id"],analysis_hash=self.data["analysis_hash"],channel="LINKEDIN",objective="Synthetic fictional rehearsal",owner="Synthetic reviewer",claim_ids=[self.records["claim"]["id"]],asset_ids=[asset["id"]],readiness_id=self.records["readiness"]["id"],store_id=self.records["store"]["id"],route_id=self.records["route"]["id"],currency="USD",budget_minor=0,duration_seconds=30)
        own=Briefs(self.store).save(APP,{"data":brief_definition})
        linked=self.workflow.save(APP,"intents",{"data":dict(self.data,brief_id=own["id"])})
        self.assertEqual(linked["data"]["brief"]["hash"],own["hash"])
        restored=Store(Path(self.tmp.name)/"linked/state.sqlite");restored.restore(self.store.export(APP))
        self.assertEqual(len(Acquisition(restored).list(APP)["intents"]),2)
        _,analysis,records,definition=ready_production(self.store,"other-acquisition")
        other=Briefs(self.store).save("other-acquisition",{"data":definition})
        with self.assertRaises(Invalid):self.workflow.save(APP,"intents",{"data":dict(self.data,brief_id=other["id"])})
        source=Library(self.store).list(APP)[0]
        Library(self.store).save(APP,dict(id=source["id"],version=source["current"]["version"],data=dict(source["current"]["data"],title="Updated source capture")))
        with self.assertRaises(Invalid):self.workflow.save(APP,"intents",{"data":self.data})
        self.assertEqual(self.workflow.list(APP)["intents"][0]["evidence_status"],"STALE_EVIDENCE")

    def test_declare_panel_stale_manifest_and_bad_contract(self):
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],activation="Changed first-value event"),app["version"])
        with self.assertRaises(Invalid):self.workflow.save(APP,"panels",{"data":panel_data(self.intent)})
        with self.assertRaises(Invalid):self.workflow.save(APP,"panels",{"data":None})

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"one/state.sqlite")
        self.data,self.records=ready_acquisition(self.store);self.workflow=Acquisition(self.store)
        self.intent=self.workflow.save(APP,"intents",{"data":self.data})
        self.panel=self.workflow.save(APP,"panels",{"data":panel_data(self.intent)})

    def tearDown(self):self.tmp.cleanup()

    def complete(self):
        for query in ("problem","comparison"):
            for repetition in (1,2):self.workflow.save(APP,"observations",{"data":answer(self.panel,query,repetition)})
        return self.workflow.report(APP,{"panel_id":self.panel["id"]})

    def test_intent_current_proof_and_educational_store(self):
        d=self.intent["data"];self.assertEqual(d["first_value"],"Saved fictional next step")
        self.assertEqual(d["demand"],"UNKNOWN");self.assertEqual(d["publication"],"NOT_RUN")
        self.assertEqual(d["records"][0]["data"]["claim"],self.records["claim"]["data"]["claim"])
        educational=self.workflow.save(APP,"intents",{"data":dict(self.data,store_id=None)})
        self.assertEqual(educational["data"]["asa_status"],"BLOCKED_STORE")
        for changes in ({"claim_id":"foreign"},{"analysis_hash":"changed"},{"territory":"usa"},{"page_url":"http://127.0.0.1"},{"native_reviewer":""}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.workflow.save(APP,"intents",{"data":dict(self.data,**changes)})
        with self.assertRaises(Invalid):self.workflow.save("sample-two","intents",{"data":self.data})
        from tests.journey_fixtures import failed
        Service(self.store).evidence(APP,dict(kind="readiness",title="Synthetic new failure",source="Synthetic receipt",data=failed(self.records["readiness"]["data"])))
        self.assertEqual(self.workflow.list(APP)["panels"][0]["evidence_status"],"STALE_EVIDENCE")
        with self.assertRaises(Invalid):self.workflow.report(APP,{"panel_id":self.panel["id"]})

    def test_fixed_panel_definition_conditions_and_revision(self):
        for changes in ({"surface":"MIXED"},{"repetitions":True},{"repetitions":6},{"queries":[]},{"queries":[dict(id="same",text="Same",partition="CALIBRATION")]*2},{"intent_hash":"wrong"},{"rubric":""}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.workflow.save(APP,"panels",{"data":panel_data(self.intent,**changes)})
        with self.assertRaises(Invalid):self.workflow.save(APP,"panels",dict(id=self.panel["id"],version=1,data=panel_data(self.intent)))
        consumer=self.workflow.save(APP,"panels",{"data":panel_data(self.intent,surface="CONSUMER_UI")})
        self.assertNotEqual(consumer["hash"],self.panel["hash"])
        revised=self.workflow.save(APP,"intents",dict(id=self.intent["id"],version=1,data=dict(self.data,problem="A changed fictional problem")))
        self.assertEqual(revised["version"],2)
        self.assertEqual(self.workflow.list(APP)["panels"][0]["evidence_status"],"STALE_EVIDENCE")
        with self.assertRaises(Invalid):self.workflow.save(APP,"observations",{"data":answer(self.panel)})

    def test_slot_validation_error_retry_and_conflict(self):
        raw=answer(self.panel);saved=self.workflow.save(APP,"observations",{"data":raw})
        self.assertEqual(self.workflow.save(APP,"observations",{"data":raw}),saved)
        with self.assertRaises(Invalid):self.workflow.save(APP,"observations",{"data":dict(raw,raw_response="Changed response")})
        for changes in ({"query_id":"foreign"},{"panel_hash":"wrong"},{"repetition":True},{"repetition":3},{"observed_at":"2020-01-01T00:00:00+00:00"},{"observed_at":"2999-01-01T00:00:00+00:00"},{"correct_citation":True,"citation_url":None},{"mention":None},{"status":"ERROR"},{"raw_response":"x"*20001},{"source_ref":""}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.workflow.save(APP,"observations",{"data":answer(self.panel,"comparison",**changes)})
        failed=answer(self.panel,"comparison",status="ERROR",raw_response="Synthetic timeout",mention=None,citation_url=None,correct_citation=None,misinformation=None)
        self.workflow.save(APP,"observations",{"data":failed})
        report=self.workflow.report(APP,{"panel_id":self.panel["id"]})["data"];h=report["partitions"]["HOLDOUT"]
        self.assertEqual((h["errors"],h["missing"],h["successful"]),(1,1,0));self.assertIsNone(h["mentions_per_answer"])

    def test_missing_pending_reviews_and_complete_pipeline_attachment(self):
        empty=self.workflow.report(APP,{"panel_id":self.panel["id"]})
        self.assertEqual(empty["data"]["partitions"]["CALIBRATION"]["missing"],2)
        with self.assertRaises(Invalid):self.workflow.attach(APP,{"report_id":empty["id"]})
        self.workflow.save(APP,"observations",{"data":answer(self.panel,correct_citation=None)})
        pending=self.workflow.report(APP,{"panel_id":self.panel["id"]})
        self.assertEqual(pending["data"]["partitions"]["CALIBRATION"]["pending_review"],1)
        with self.assertRaises(Invalid):self.workflow.attach(APP,{"report_id":pending["id"]})
        other=self.workflow.save(APP,"panels",{"data":panel_data(self.intent)})
        for query in ("problem","comparison"):
            for repetition in (1,2):self.workflow.save(APP,"observations",{"data":answer(other,query,repetition)})
        report=self.workflow.report(APP,{"panel_id":other["id"]});part=report["data"]["partitions"]["HOLDOUT"]
        self.assertEqual((part["expected"],part["attempted"],part["correct_exact_destination"]),(2,2,2))
        attached=self.workflow.attach(APP,{"report_id":report["id"]})
        self.assertEqual(self.workflow.attach(APP,{"report_id":report["id"]}),attached)
        record=next(r for r in self.store.records(APP) if r["id"]==attached["id"])
        self.assertEqual(record["data"]["panel_report_hash"],report["hash"]);self.assertEqual(len(record["data"]["analysis"]["aeo"]),4)
        self.assertEqual(len(Service(self.store).workspace(APP)["acquisition"]["panels"]),2)

    def test_portable_exact_replay_and_tamper_atomic(self):
        report=self.complete();self.workflow.attach(APP,{"report_id":report["id"]});snapshot=self.store.export(APP)
        restored=Store(Path(self.tmp.name)/"restored/state.sqlite");restored.restore(snapshot)
        self.assertEqual(restored.export(APP)["payload"]["acquisition"],snapshot["payload"]["acquisition"])
        self.assertEqual(Acquisition(restored).list(APP)["panels"][0]["evidence_status"],"CURRENT")
        for index,change in enumerate(("scope","score","omission","panel","slot","identity")):
            bad=copy.deepcopy(snapshot);a=bad["payload"]["acquisition"]
            if change=="scope":row=a["observations"][0]["versions"][0];row["app_id"]="sample-two"
            elif change=="score":row=a["reports"][0]["versions"][0];row["data"]["partitions"]["HOLDOUT"]["mentions"]=99
            elif change=="omission":
                row=a["reports"][0]["versions"][0];d=row["data"];row["data"]=calculate(d["panel"],d["observations"][:-1],d["evaluated_at"])
            elif change=="panel":row=a["panels"][0]["versions"][0];row["data"]["definition"]["intent_hash"]="wrong"
            elif change=="slot":row=a["observations"][0]["versions"][0];row["data"]["query_id"]="unknown"
            else:a["reports"][0]["id"]={};row=None
            if row is not None:row["hash"]=digest(row["data"])
            bad["sha256"]=digest(bad["payload"]);target=Store(Path(self.tmp.name)/f"bad{index}/state.sqlite")
            with self.subTest(change=change),self.assertRaises(Invalid):target.restore(bad)
            self.assertNotIn(APP,[r["id"] for r in target.apps()]);self.assertFalse((target.path.parent/"files"/APP).exists())
        old=copy.deepcopy(snapshot);old["payload"].pop("acquisition");old["sha256"]=digest(old["payload"])
        target=Store(Path(self.tmp.name)/"old/state.sqlite");target.restore(old);self.assertEqual(Acquisition(target).list(APP)["panels"],[])

    def test_reload_scope_and_bounded_report_performance(self):
        self.complete();start=time.monotonic()
        for _ in range(10):self.workflow.report(APP,{"panel_id":self.panel["id"]})
        elapsed=time.monotonic()-start;self.assertLess(elapsed,10)
        print(f"LOCAL_SYNTHETIC_PANEL_REPORTS count=10 elapsed_seconds={elapsed:.6f}")
        reopened=Acquisition(Store(self.store.path));self.assertEqual(len(reopened.list(APP)["reports"]),11)
        self.assertEqual(reopened.list("sample-two")["intents"],[])
        with self.assertRaises(Invalid):reopened.report("sample-two",{"panel_id":self.panel["id"]})
        with self.assertRaises(Invalid):reopened.save(APP,"unknown",{"data":{}})


if __name__=="__main__":unittest.main()
