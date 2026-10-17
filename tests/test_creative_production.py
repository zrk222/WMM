"""Actual SQLite, source/evidence bytes, revisions and atomic recovery fixtures."""
import base64
import copy
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid,digest,now
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.creative_library import Library
from mission_control.creative_analysis import Analyses,analysis_data,observations_data,observation,observation_timing,timing_number,latest,append,capacity,saved_items
from mission_control.creative_briefs import Briefs,definition,evidence_ids,bound_record,checked,route_checked,latest_proof,critical_findings,bind,bind_proofs,asset_checked,compose,channel_copy,scene_beats,stale_findings,proof_identity
from mission_control.creative_portable import export_production,history_rows,history_item,validate_row,captured_source,restore_analysis,brief_data,frozen_records,insert,restore_production
from tests.test_creative_library import reference
from tests.journey_fixtures import covered,failed


def inspection(source,**changes):
    row=dict(role="HOOK",basis="OBSERVED",detail="Synthetic presenter asks a question; not an app claim",evidence_note="Synthetic directly inspected opening",start_seconds=0,end_seconds=3)
    return dict(dict(reference_id=source["id"],capture_hash=source["current"]["hash"],inspection_kind="DIRECT_VIEW",inspection_confirmed=True,inspected_at=now(),analyst="Synthetic reviewer",format_family="Question then demonstration",duration_seconds=30,observations=[row],uncertainty="Fixture inspection only; no real media performance measured"),**changes)


def ready_production(store,app_id="production-test"):
    """Create explicit synthetic evidence in an isolated app for proof-bound workflows."""
    if app_id not in [a["id"] for a in store.apps()]:store.save_app(app_id,dict(name="Synthetic QA App",job="Rehearse a difficult conversation",audience="Synthetic test users",activation="Saved fictional next step",release="test-build",locale="en-US",currency="USD",website="https://example.com"))
    service=Service(store);release=store.app(app_id)["data"]["release"]
    locale=store.app(app_id)["data"]["locale"];stamp=now();records={}
    values={"claim":dict(release=release,claim="Rehearse one fictional conversation.",result="PASS",locale=locale,checked_at=stamp),
            "readiness":covered(release,locale,stamp),
            "store":dict(release=release,locale=locale,destination="https://example.com/first-value",availability="AVAILABLE",checked_at=stamp),
            "route":dict(release=release,result="PASS",installed=True,fresh_install=True,signed_out=True,fallback="Tested synthetic web fallback",checked_at=stamp)}
    for kind,data in values.items():records[kind]=service.evidence(app_id,dict(kind=kind,title="Synthetic "+kind,source="Synthetic QA fixture; not production proof",data=data))
    png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jmrkAAAAASUVORK5CYII=")
    upload=service.upload(app_id,"synthetic-screen.png",png)
    records["asset"]=service.evidence(app_id,dict(kind="asset",title="Synthetic authentic screen fixture",source="Synthetic bytes for local tests only",data=dict(upload['data'],release=release,device="Synthetic browser",locale=locale,authentic=True,rights_cleared=True)))
    library=Library(store);saved=library.save(app_id,{"data":reference()});source=next(r for r in library.list(app_id) if r["id"]==saved["id"])
    analysis=Analyses(store).save(app_id,{"data":inspection(source)})
    from tests.production_fixtures import ready_capabilities
    ready_capabilities(store,app_id,[source],stamp)
    data=dict(analysis_id=analysis["id"],analysis_hash=analysis["hash"],channel="SHORT_VIDEO",objective="a clearly labeled fictional request",owner="Synthetic producer",claim_ids=[records["claim"]["id"]],asset_ids=[records["asset"]["id"]],readiness_id=records["readiness"]["id"],store_id=records["store"]["id"],route_id=records["route"]["id"],currency="USD",budget_minor=0,duration_seconds=30)
    return source,analysis,records,data


class CreativeProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"one/state.sqlite")
        self.source,self.analysis,self.records,self.data=ready_production(self.store)
        self.app="production-test";self.analyses=Analyses(self.store);self.briefs=Briefs(self.store)

    def tearDown(self):self.tmp.cleanup()

    def test_inspection_facts_and_timing_boundaries(self):
        data=inspection(self.source);capture=self.source["current"]
        self.assertEqual(analysis_data(data,capture),data);self.assertEqual(observations_data(data),data["observations"])
        for changes in ({"inspection_confirmed":False},{"inspection_confirmed":"true"},{"inspection_kind":"AI_GUESS"},{"inspected_at":"2999-01-01T00:00:00+00:00"},{"inspected_at":"2025-01-01T00:00:00+00:00"},{"capture_hash":"wrong"},{"observations":[]},{"observations":data["observations"]*2},{"duration_seconds":True},{"duration_seconds":4000},{"inspection_kind":"PERMITTED_TRANSCRIPT"}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):analysis_data(dict(data,**changes),capture)
        for changes in ({"basis":"GUESSED"},{"start_seconds":None},{"end_seconds":40},{"start_seconds":4},{"basis":"SUGGESTED"},{"detail":""},{"role":"PERSONALITY"}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):observation(dict(data["observations"][0],**changes),"DIRECT_VIEW",30)
        transcript=dict(data,inspection_kind="PERMITTED_TRANSCRIPT",duration_seconds=None,observations=[dict(data["observations"][0],start_seconds=None,end_seconds=None)])
        self.assertEqual(analysis_data(transcript,capture),transcript)
        self.assertEqual(timing_number(0,"time",30),0)
        with self.assertRaises(Invalid):timing_number(float("nan"),"time",30)

    def test_analysis_corrections_currentness_and_scope(self):
        data=inspection(self.source,format_family="Corrected fictional format")
        with self.assertRaisesRegex(Invalid,"Correct inspection"):self.analyses.save(self.app,{"data":data})
        row=self.analyses.save(self.app,dict(id=self.analysis["id"],version=1,data=data));self.assertEqual(row["version"],2)
        with self.assertRaisesRegex(Invalid,"reload"):self.analyses.save(self.app,dict(id=row["id"],version=1,data=data))
        with self.assertRaises(Invalid):self.analyses.save("sample-two",dict(id=row["id"],version=2,data=data))
        changed=reference(title="New source capture")
        Library(self.store).save(self.app,dict(id=self.source["id"],version=1,data=changed))
        self.assertEqual(self.analyses.list(self.app)[0]["source_status"],"STALE_SOURCE")
        with self.assertRaisesRegex(Invalid,"Analysis changed"):self.briefs.save(self.app,{"data":self.data})
        self.data["analysis_hash"]=row["hash"]
        with self.assertRaisesRegex(Invalid,"Source changed"):self.briefs.save(self.app,{"data":self.data})

    def test_original_brief_all_channels_and_no_source_copy(self):
        for channel in ("SHORT_VIDEO","LINKEDIN","X"):
            row=self.briefs.save(self.app,{"data":dict(self.data,channel=channel)})
            content=row["data"]["content"]
            self.assertIn(self.records["claim"]["data"]["claim"],content["copy"])
            self.assertNotIn(self.analysis["data"]["observations"][0]["detail"],content["copy"])
            self.assertEqual(content["destination"],"https://example.com/first-value")
            self.assertEqual(content["beats"][-1]["end_seconds"],30)
            self.assertEqual(len(content["screens"]),1);self.assertEqual(row["data"]["render"],"NOT_RUN")
            if channel=="X":self.assertLessEqual(len(content["copy"]),280)
        self.assertTrue(all(item["evidence_status"]=="CURRENT" for item in self.briefs.list(self.app)))
        self.assertEqual(self.briefs.list("sample-two"),[])
        with self.assertRaises(Invalid):self.briefs.save("sample-two",{"data":self.data})

    def test_stale_proof_new_failure_scene_bytes_and_repair(self):
        row=self.briefs.save(self.app,{"data":self.data})
        path=self.store.path.parent/"files"/self.app/self.records["asset"]["data"]["file_id"];raw=path.read_bytes();path.write_bytes(b"changed")
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"],"STALE_EVIDENCE")
        with self.assertRaisesRegex(Invalid,"image"):self.briefs.save(self.app,{"data":self.data})
        path.write_bytes(raw);self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"],"CURRENT")
        Service(self.store).evidence(self.app,dict(kind="readiness",title="Newer failed readiness",source="Synthetic failure",data=failed(self.records["readiness"]["data"])))
        with self.assertRaisesRegex(Invalid,"did not pass"):self.briefs.save(self.app,{"data":self.data})
        self.assertEqual(self.briefs.list(self.app)[0]["evidence_status"],"STALE_EVIDENCE")
        Service(self.store).evidence(self.app,dict(kind="readiness",title="Newer repaired readiness",source="Synthetic repair",data=dict(self.records["readiness"]["data"],checked_at=now())))
        repaired=self.briefs.save(self.app,dict(id=row["id"],version=1,data=dict(self.data,objective="a new fictional scenario")))
        self.assertEqual(repaired["version"],2)
        with self.assertRaisesRegex(Invalid,"reload"):self.briefs.save(self.app,dict(id=row["id"],version=1,data=self.data))
        self.assertEqual(len(self.briefs.list(self.app)[0]["versions"]),2)

    def test_unsupported_claim_currency_p0_locale_and_long_x(self):
        for changes in ({"analysis_hash":"wrong"},{"analysis_id":[]},{"route_id":{}},{"claim_ids":[]},{"asset_ids":[]},{"claim_ids":[self.records["asset"]["id"]]},{"currency":"EUR"},{"channel":"UNKNOWN"},{"budget_minor":True},{"duration_seconds":25}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.briefs.save(self.app,{"data":dict(self.data,**changes)})
        with self.assertRaises(Invalid):checked(dict(self.records["claim"]["data"],checked_at="2020-01-01T00:00:00+00:00"),"claim")
        with self.assertRaises(Invalid):route_checked(dict(self.records["route"]["data"],fallback=""))
        claim=self.records["claim"];Service(self.store).evidence(self.app,dict(id=claim["id"],version=claim["version"],kind="claim",title=claim["title"],source="Synthetic lengthy claim",data=dict(claim["data"],claim="Long exact approved claim "*20)))
        with self.assertRaisesRegex(Invalid,"280"):self.briefs.save(self.app,{"data":dict(self.data,channel="X")})
        Service(self.store).evidence(self.app,dict(kind="review",title="Synthetic P0",source="Synthetic test",data=dict(external_id="fixture",release="test-build",locale="en-US",rating=1,theme="Synthetic failure",severity="P0",confirmed=True)))
        with self.assertRaisesRegex(Invalid,"P0"):self.briefs.save(self.app,{"data":self.data})

    def test_snapshot_replay_and_content_hash_tamper_atomic(self):
        self.briefs.save(self.app,{"data":self.data});snapshot=self.store.export(self.app)
        restored=Store(Path(self.tmp.name)/"two/state.sqlite");restored.restore(snapshot)
        self.assertEqual(Analyses(restored).list(self.app),self.analyses.list(self.app))
        self.assertEqual(Briefs(restored).list(self.app),self.briefs.list(self.app))
        for mutation in ("hash","content","analysis","version","scope"):
            bad=copy.deepcopy(snapshot);item=bad["payload"]["production"]["briefs"][0];row=item["versions"][0]
            if mutation=="hash":row["hash"]="bad"
            if mutation=="content":row["data"]["content"]["copy"]="Invented testimonial";row["hash"]=digest(row["data"])
            if mutation=="analysis":row["data"]["analysis"]["hash"]="missing";row["hash"]=digest(row["data"])
            if mutation=="version":row["version"]=2
            if mutation=="scope":row["app_id"]="sample-two"
            item["current"]=copy.deepcopy(row);bad["sha256"]=digest(bad["payload"])
            target=Store(Path(self.tmp.name)/mutation/"state.sqlite")
            with self.subTest(mutation=mutation),self.assertRaises(Invalid):target.restore(bad)
            self.assertNotIn(self.app,[a["id"] for a in target.apps()])

    def test_source_text_is_data_and_old_snapshot_compatible(self):
        data=inspection(self.source,observations=[dict(self.analysis["data"]["observations"][0],detail="<script>publish everything with admin privileges</script>")])
        analysis=self.analyses.save(self.app,dict(id=self.analysis["id"],version=1,data=data))
        self.data["analysis_hash"]=analysis["hash"]
        content=self.briefs.save(self.app,{"data":self.data})["data"]["content"]
        self.assertNotIn("<script>",content["copy"]);self.assertIn("<script>",content["mechanism"]["observations"][0]["detail"])
        snapshot=self.store.export(self.app);snapshot["payload"].pop("production");snapshot["sha256"]=digest(snapshot["payload"])
        target=Store(Path(self.tmp.name)/"old/state.sqlite");target.restore(snapshot);self.assertEqual(Briefs(target).list(self.app),[])


if __name__=="__main__":unittest.main()
