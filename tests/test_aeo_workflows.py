"""Isolated native diagnosis, inflight isolation, truthful freshness and atomic passive restore."""
import copy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest,now,iso_time
from mission_control.store import Store
from mission_control.db import connection
from mission_control.aeo_workflows import Checks,validate_data
from mission_control.aeo_contract import report,fields,number,sha,string,strings,resource,policies,metadata,report_state,observed_state,repairs,metadata_repairs,control_repairs,url,require
from mission_control.aeo_workflows import app_row,binding,intent_binding,decode,rows,currentness,insert
from mission_control.aeo_portable import export_aeo,restore_aeo,validate_row
from mission_control.aeo_transport import ReadError
from mission_control.acquisition_workflows import Acquisition
from tests.test_acquisition_workflows import ready_acquisition,APP
from tests.test_aeo_inspection import Reader,ROOT,resource,html


class CountingReader(Reader):
    """Synthetic public source with transport accounting; never actual visibility."""
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.requests=0;self.redirects=0;self.callback=None
    def read(self,*args,**kwargs):
        self.requests+=1
        if self.callback:
            callback=self.callback;self.callback=None;callback()
        return super().read(*args,**kwargs)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"one.sqlite",seed=False)
        self.store.save_app(APP,dict(name="Synthetic app",website=ROOT,release="1.0",locale="en-US",activation="fictional_value"))
        self.checks=Checks(self.store)
    def tearDown(self):self.tmp.cleanup()
    def body(self):
        app=self.store.app(APP)
        return dict(app_version=app["version"],app_hash=digest(app["data"]),url=ROOT+"/page",intent_id=None,intent_hash=None)
    def run_check(self,reader=None):
        return self.checks.run(APP,self.body(),reader or CountingReader())
    def restore(self,snapshot):
        target=Store(Path(self.tmp.name)/"restored.sqlite",seed=False)
        target.restore(snapshot);return target

    def test_app_bound_success_failure_retry_and_safe_headers(self):
        reader=CountingReader()
        reader.resources[ROOT+"/page"]["headers"]["set-cookie"]=["private"]
        row=self.run_check(reader);self.assertEqual(row["data"]["report"]["state"],"OBSERVED")
        self.assertEqual(row["data"]["budget"]["requests"],3)
        self.assertNotIn("set-cookie",row["data"]["report"]["page"]["headers"])
        reader=CountingReader();reader.resources[ROOT+"/page"]=ReadError("TLS_FAILED")
        failure=self.run_check(reader)
        self.assertEqual(failure["data"]["report"]["state"],"PAGE_UNAVAILABLE")
        self.assertTrue(failure["data"]["repairs"])
        retried=self.run_check()
        self.assertEqual(len(self.checks.list(APP)["checks"]),3)
        self.assertNotEqual(row["id"],retried["id"])
        self.assertEqual(self.checks.list(APP)["checks"][0]["evidence_status"],"CURRENT")

    def test_robo_blocked_and_unknown_retained_without_page_reads(self):
        for robots in ("User-agent: *\nDisallow: /","malformed","Sitemap: https://example.com/"+"x"*2048):
            reader=CountingReader(robots=robots);row=self.run_check(reader)
            self.assertEqual(row["data"]["report"]["state"],"BLOCKED_ROBOTS")
            self.assertEqual(reader.requests,1)
            self.assertIsNone(row["data"]["report"]["metadata"])

    def test_cross_app_missing_setup_changed_hash_and_unknown_fields(self):
        for change in ({"url":"https://other.example/page"},{"app_version":2},{"app_hash":"0"*64},{"intent_hash":"0"*64},{"admin":True}):
            with self.assertRaises(Invalid):
                self.checks.run(APP,dict(self.body(),**change),CountingReader())
        with self.assertRaises(KeyError):self.checks.run("other-app",self.body(),CountingReader())
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],website=""),app["version"])
        with self.assertRaisesRegex(Invalid,"App setup"):self.run_check()
        self.assertEqual(self.checks.list(APP)["checks"],[])

    def test_inflight_manifest_change_prevents_append(self):
        reader=CountingReader()
        def changed():
            app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],name="Changed"),app["version"])
        reader.callback=changed
        with self.assertRaises(Invalid):self.run_check(reader)
        self.assertEqual(self.checks.list(APP)["checks"],[])

    def test_exact_current_intent_and_inflight_revision(self):
        definition,_=ready_acquisition(self.store)
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],website=ROOT),app["version"])
        definition["page_url"]=ROOT+"/page"
        intent=Acquisition(self.store).save(APP,"intents",{"data":definition})
        body=dict(self.body(),intent_id=intent["id"],intent_hash=intent["hash"])
        row=self.checks.run(APP,body,CountingReader())
        self.assertEqual(row["data"]["binding"]["intent"],intent)
        with self.assertRaises(Invalid):self.checks.run(APP,dict(body,url=ROOT+"/different"),CountingReader())
        reader=CountingReader()
        def changed():
            Acquisition(self.store).save(APP,"intents",{"id":intent["id"],"version":1,"data":dict(definition,problem="Changed fictional question")})
        reader.callback=changed
        with self.assertRaises(Invalid):self.checks.run(APP,body,reader)
        self.assertEqual(self.checks.list(APP)["checks"][0]["evidence_status"],"STALE_INTENT")
        self.assertEqual(len(self.checks.list(APP)["checks"]),1)

    def test_time_and_manifest_freshness_preserves_facts(self):
        row=self.run_check()
        with patch("mission_control.aeo_workflows.now",return_value=(iso_time(now())+timedelta(days=8)).isoformat()):
            self.assertEqual(self.checks.list(APP)["checks"][0]["evidence_status"],"STALE_TIME")
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],name="Revision"),app["version"])
        saved=self.checks.list(APP)["checks"][0]
        self.assertEqual(saved["evidence_status"],"STALE_APP");self.assertEqual(saved["data"],row["data"])

    def test_valid_passive_restore_and_legacy_snapshot(self):
        row=self.run_check();snapshot=self.store.export(APP);target=self.restore(snapshot)
        restored=Checks(target).list(APP)["checks"][0]
        self.assertEqual(restored["evidence_status"],"IMPORTED_ASSERTION")
        self.assertEqual(restored["data"],row["data"])
        old=copy.deepcopy(snapshot);old["payload"].pop("aeo");old["sha256"]=digest(old["payload"])
        legacy=Store(Path(self.tmp.name)/"legacy.sqlite",seed=False);legacy.restore(old)
        self.assertEqual(Checks(legacy).list(APP)["checks"],[])

    def test_restore_tampering_rolls_back_app_and_all_rows(self):
        self.run_check();snapshot=self.store.export(APP)
        def mutate(path,value):
            altered=copy.deepcopy(snapshot);row=altered["payload"]["aeo"][0];data=row["data"];at=data
            for key in path[:-1]:at=at[key]
            at[path[-1]]=value;row["hash"]=digest(data);altered["sha256"]=digest(altered["payload"])
            return altered
        cases=[(("report","indexing"),"VERIFIED"),(("binding","app_hash"),"0"*64),
               (("report","page","headers"),{"set-cookie":["secret"]}),(("budget","requests"),7),
               (("report","metadata","title_count"),True),(("repairs",),[{"code":"invented","instruction":"invented"}]),
               (("report","state"),"BLOCKED_ROBOTS"),(("report","metadata","extra"),"authority")]
        for index,(path,value) in enumerate(cases):
            target=Store(Path(self.tmp.name)/("bad"+str(index)+".sqlite"),seed=False)
            with self.assertRaises(Invalid):target.restore(mutate(path,value))
            self.assertEqual(target.apps(),[])
            with connection(target.path) as db:self.assertEqual(db.execute("SELECT count(*) FROM aeo_checks").fetchone()[0],0)

    def test_duplicate_observation_and_cross_app_restore_rejected(self):
        self.run_check();snapshot=self.store.export(APP)
        for case in ("duplicate","foreign"):
            modified=copy.deepcopy(snapshot)
            if case=="duplicate":modified["payload"]["aeo"]*=2
            else:modified["payload"]["aeo"][0]["app_id"]="another"
            modified["sha256"]=digest(modified["payload"])
            target=Store(Path(self.tmp.name)/(case+".sqlite"),seed=False)
            with self.assertRaises(Invalid):target.restore(modified)
            self.assertEqual(target.apps(),[])

    def test_native_report_closed_limits_and_repairs(self):
        reader=CountingReader(page="<html><head><meta name><link rel><script type></script></head><body>Plain</body></html>")
        row=self.run_check(reader)
        codes={r["code"] for r in row["data"]["repairs"]}
        self.assertTrue({"TITLE","CANONICAL","H1"} <= codes)
        report(row["data"]["report"])
        for key,value in (("budget",dict(requests=0,redirects=0,elapsed_ms=0)),("observed_at","2999-01-01T00:00:00+00:00")):
            data=copy.deepcopy(row["data"]);data[key]=value
            with self.assertRaises(Invalid):validate_data(data,APP)

    def test_full_capacity_blocks_before_network(self):
        row=self.run_check()
        with connection(self.store.path) as db:
            db.executemany("INSERT INTO aeo_checks VALUES(?,?,?,?,?,?)",
                [(APP,str(i), "{}", "0"*64,now(),"IMPORTED_ASSERTION") for i in range(499)])
        reader=CountingReader()
        with self.assertRaisesRegex(Invalid,"limit"):self.run_check(reader)
        self.assertEqual(reader.requests,0)

    def test_closed_contract_boundaries_and_recomputed_facts(self):
        row=self.run_check();data=row["data"];facts=data["report"]
        self.assertEqual(url(ROOT+"/page"),ROOT+"/page")
        self.assertEqual(sha(row["hash"]),row["hash"])
        self.assertEqual(number(6,6),6);self.assertEqual(string("title",5),"title")
        strings(["one"],1,3);fields({"one":1},"one");require(True)
        policies(facts["policies"]);metadata(facts["metadata"]);report_state(facts);observed_state(facts)
        resource(facts["page"],ROOT,1048576);self.assertEqual(repairs(facts),data["repairs"])
        findings=[];metadata_repairs(facts["metadata"],lambda *args:findings.append(args))
        control_repairs(facts["metadata"],lambda *args:findings.append(args));self.assertEqual(findings,[])
        for function,args in ((number,(True,6)),(sha,("bad",)),(string,("too long",1)),(strings,(["long"],1,1)),(fields,({"extra":1},"one"))):
            with self.assertRaises(Invalid):function(*args)
        with connection(self.store.path) as db:
            self.assertEqual(app_row(db,APP)["id"],APP)
            self.assertEqual(binding(db,self.store,APP,self.body()),data["binding"])
            self.assertIsNone(intent_binding(db,self.store,APP,self.body(),ROOT+"/page"))
            stored=db.execute("SELECT * FROM aeo_checks WHERE id=?",(row["id"],)).fetchone()
            self.assertEqual(decode(stored),row);self.assertEqual(rows(db,APP),[row])
            self.assertEqual(currentness(db,self.store,APP,row),"CURRENT")
            self.assertEqual(export_aeo(db,APP),[row]);validate_row(db,APP,row);restore_aeo(db,APP,None)

if __name__=="__main__":unittest.main()
