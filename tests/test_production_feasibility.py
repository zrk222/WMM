"""Real SQLite capability enforcement, frozen history and atomic recovery."""
import copy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import time
import unittest
from mission_control.common import Invalid,digest,now
from mission_control.db import connection
from mission_control.store import Store
from mission_control.creative_briefs import Briefs
from mission_control.creative_library import Library
from mission_control.production_contract import declaration
from mission_control.production_feasibility import Capabilities,assess,context
from tests.production_fixtures import profile,requirement
from tests.test_creative_production import ready_production
from tests.test_creative_ranking import ready_ranking,APP
from mission_control.creative_ranking import Rankings

class ProductionFeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"source/state.sqlite")
        self.source,self.analysis,self.records,self.brief=ready_production(self.store)
        self.app="production-test";self.service=Capabilities(self.store)

    def tearDown(self):self.tmp.cleanup()

    def revise(self,kind,**changes):
        row=self.service.list(self.app)[kind][0]
        return self.service.save(self.app,kind,dict(id=row["id"],version=row["current"]["version"],data=dict(row["current"]["data"],**changes)))

    def test_exact_typed_contract_boundaries(self):
        cases=[("profile",dict(executions=[])),("profile",dict(talent=["NONE","NONE"])),("profile",dict(channels=["UNKNOWN"])),
               ("profile",dict(capture_available=1)),("profile",dict(editing_level=True)),("profile",dict(time_minutes=0)),
               ("profile",dict(cost_minor=-1)),("profile",dict(cost_minor=1000000000001)),("profile",dict(checked_at="2999-01-01T00:00:00+00:00")),
               ("requirement",dict(rights_available="true")),("requirement",dict(execution="MADE_UP")),("requirement",dict(narrative="MAGIC"))]
        for kind,change in cases:
            data=profile(self.store,self.app) if kind=="profile" else requirement(self.source)
            with self.subTest(change=change),self.assertRaises(Invalid):declaration(dict(data,**change),kind)
        self.assertEqual(declaration(requirement(self.source,execution="UNKNOWN"),"requirement")["execution"],"UNKNOWN")

    def test_missing_capability_blocks_brief_not_fake_readiness(self):
        with connection(self.store.path) as db:db.execute("DELETE FROM production_profiles WHERE app_id=?",(self.app,))
        result=self.service.list(self.app)["evaluations"][0]
        self.assertEqual(result["status"],"BLOCKED");self.assertIn("Set up",result["reasons"][0])
        with self.assertRaisesRegex(Invalid,"Production blocked"):Briefs(self.store).save(self.app,{"data":self.brief})

    def test_each_constraint_blocks_and_revision_recovers(self):
        for changes in [dict(execution="UNKNOWN"),dict(talent="CONSENTED_CREATOR",rights_available=False),dict(cost_minor=100001),dict(time_minutes=10081)]:
            if "time_minutes" in changes:
                with self.assertRaises(Invalid):self.revise("requirement",**changes)
                continue
            self.revise("requirement",**changes)
            self.assertEqual(self.service.list(self.app)["evaluations"][0]["status"],"BLOCKED")
            with self.assertRaises(Invalid):Briefs(self.store).save(self.app,{"data":self.brief})
            row=self.service.list(self.app)["requirement"][0]
            self.service.save(self.app,"requirement",dict(id=row["id"],version=row["current"]["version"],data=requirement(self.source)))
        self.assertEqual(self.service.list(self.app)["evaluations"][0]["status"],"READY")

    def test_capture_audio_editing_time_and_channel_limits(self):
        for changes in (dict(capture_available=False),dict(audio=["MUSIC"]),dict(editing_level=0),dict(time_minutes=1),dict(executions=["HOST"]),dict(talent=["FOUNDER"])):
            self.revise("profile",**changes)
            self.assertEqual(self.service.list(self.app)["evaluations"][0]["status"],"BLOCKED")
            row=self.service.list(self.app)["profile"][0]
            self.service.save(self.app,"profile",dict(id=row["id"],version=row["current"]["version"],data=profile(self.store,self.app)))
        self.revise("profile",channels=["LINKEDIN"])
        with self.assertRaisesRegex(Invalid,"Channel"):Briefs(self.store).save(self.app,{"data":self.brief})

    def test_optimistic_identity_scope_and_saved_history(self):
        row=self.service.list(self.app)["profile"][0]
        self.revise("profile",source="Second explicit synthetic review")
        with self.assertRaises(Invalid):self.service.save(self.app,"profile",dict(id=row["id"],version=1,data=profile(self.store,self.app)))
        with self.assertRaises(Invalid):self.service.save(self.app,"profile",{"data":profile(self.store,self.app)})
        with self.assertRaises(Invalid):self.service.save("sample-two","profile",dict(id=row["id"],version=2,data=profile(self.store,"sample-two")))
        history=self.service.list(self.app)["profile"][0]
        self.assertEqual([r["version"] for r in history["versions"]],[1,2])
        self.assertEqual(history,Capabilities(Store(self.store.path)).list(self.app)["profile"][0])

    def test_source_app_changes_expiry_and_future_block(self):
        stamp=now()
        with connection(self.store.path) as db:inputs=context(db,self.app)
        self.assertEqual(assess(inputs,self.source,digest(self.store.app(self.app)["data"]),stamp)["status"],"READY")
        future=(datetime.now(timezone.utc)+timedelta(days=31)).isoformat()
        self.assertEqual(assess(inputs,self.source,digest(self.store.app(self.app)["data"]),future)["status"],"BLOCKED")
        old="2020-01-01T00:00:00+00:00"
        self.assertEqual(assess(inputs,self.source,digest(self.store.app(self.app)["data"]),old)["status"],"BLOCKED")
        self.assertEqual(assess(inputs,self.source,"changed",stamp)["status"],"BLOCKED")
        changed=copy.deepcopy(self.source);changed["current"]["hash"]="changed"
        self.assertEqual(assess(inputs,changed,digest(self.store.app(self.app)["data"]),stamp)["status"],"BLOCKED")

    def test_brief_freezes_current_rows_and_revisions_mark_it_stale(self):
        saved=Briefs(self.store).save(self.app,{"data":self.brief})
        self.assertEqual(saved["data"]["production"]["profile"]["version"],1)
        self.revise("profile",source="Changed team review")
        self.assertEqual(Briefs(self.store).list(self.app)[0]["evidence_status"],"STALE_EVIDENCE")
        self.assertEqual(saved["data"]["production"]["profile"]["version"],1)

    def test_ranking_excludes_unsuitable_before_slate_and_recovers(self):
        sources=ready_ranking(self.store,count=2);ranking=Rankings(self.store);caps=Capabilities(self.store)
        row=caps.list(APP)["requirement"][0]
        caps.save(APP,"requirement",dict(id=row["id"],version=1,data=dict(row["current"]["data"],rights_available=False)))
        result=ranking.run(APP,{"reference_ids":[s["id"] for s in sources]})["data"]
        self.assertEqual(result["coverage"]["eligible"],1)
        blocked=next(r for r in result["rows"] if not r["eligible"])
        self.assertNotIn(blocked["reference_id"],result["slate"]["selected"])
        self.assertIn("rights",blocked["exclusion"])

    def test_snapshot_frozen_rows_and_atomic_forgery_rejection(self):
        Briefs(self.store).save(self.app,{"data":self.brief})
        original=self.store.export(self.app)
        target=Store(Path(self.tmp.name)/"good/state.sqlite");target.restore(original)
        self.assertEqual(target.export(self.app)["payload"]["capabilities"],original["payload"]["capabilities"])
        for mutation in ("foreign","hash","detached","infeasible","duplicate"):
            bad=copy.deepcopy(original);group=bad["payload"]["capabilities"]["profile"][0];row=group["versions"][0]
            if mutation=="foreign":row["app_id"]="sample-two"
            if mutation=="hash":row["hash"]="bad"
            if mutation=="duplicate":bad["payload"]["capabilities"]["profile"].append(copy.deepcopy(group))
            if mutation=="detached":bad["payload"]["capabilities"]["profile"]=[]
            if mutation=="infeasible":
                row["data"]["channels"]=["X"];row["hash"]=digest(row["data"])
                brief=bad["payload"]["production"]["briefs"][0]
                brief["versions"][0]["data"]["production"]["profile"]=copy.deepcopy(row)
                brief["versions"][0]["hash"]=digest(brief["versions"][0]["data"]);brief["current"]=copy.deepcopy(brief["versions"][0])
            group["current"]=copy.deepcopy(row);bad["sha256"]=digest(bad["payload"])
            fresh=Store(Path(self.tmp.name)/mutation/"state.sqlite")
            with self.subTest(mutation=mutation),self.assertRaises(Invalid):fresh.restore(bad)
            self.assertNotIn(self.app,[a["id"] for a in fresh.apps()])
            self.assertFalse((fresh.path.parent/"files"/self.app).exists())

    def test_local_evaluation_performance_and_no_jobs(self):
        start=time.monotonic()
        for _ in range(100):self.service.list(self.app)
        elapsed=time.monotonic()-start;self.assertLess(elapsed,10)
        with connection(self.store.path) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],0)
        print(f"CAPABILITY_LOCAL_100_READS_SECONDS={elapsed:.6f}")

if __name__=="__main__":unittest.main()
