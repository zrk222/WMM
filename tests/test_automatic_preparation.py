"""Automatic local drafts refresh without claims, queues or provider side effects."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mission_control.automatic_preparation import prepare, check_scope, group_needs, source_binding
from mission_control.common import Invalid, now
from mission_control.db import connection
from mission_control.service import Service
from mission_control.store import Store
from tests.journey_fixtures import covered


class AutomaticPreparationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/"test.sqlite")
        app=self.store.app("sample-one")
        self.store.save_app("sample-one",dict(app["data"],release="synthetic-build",job="Synthetic task",
            audience="Synthetic audience",activation="Synthetic activation",locale="en-US"),app["version"])
        self.service=Service(self.store)

    def evidence(self):
        return self.store.save_record("sample-one",{"kind":"readiness","title":"Synthetic readiness",
            "source":"Synthetic only","data":covered('synthetic-build')})

    def counts(self):
        with connection(self.store.path) as db:
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {name:db.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0] for name in tables}

    def test_current_read_without_writes_or_provider_requests(self):
        before=self.counts()
        with patch("urllib.request.urlopen",side_effect=AssertionError("No network on preview")):
            first=self.service.workspace("sample-one")["preparation"]
            second=self.service.workspace("sample-one")["preparation"]
        self.assertEqual(self.counts(),before)
        self.assertEqual(first["source_hash"],second["source_hash"])
        self.assertEqual(len(first["outputs"]),12)
        self.assertEqual(first["spend_minor"],0)
        self.assertFalse(first["automatic_external_writes"])
        self.assertFalse(first["durable_history"])
        self.assertEqual(first["external_execution"],"NOT_RUN")
        self.assertTrue(all(o["packet"]["local_status"]==o["status"] for o in first["outputs"]))
        self.assertTrue(any(o["packet"]["local_status"]=="BLOCKED" for o in first["outputs"]))
        messages=[n["message"] for n in first["needs"]]
        self.assertEqual(len(messages),len(set(messages)))
        self.assertFalse(any(m.startswith("Finish stage ") for m in messages))
        self.assertTrue(any("Finish stage " in m for o in first["outputs"] for m in o["missing"]))
        for need in first["needs"]:
            self.assertEqual(need["stages"],[o["stage"] for o in first["outputs"] if need["message"] in o["missing"]])

    def test_source_changes_and_failed_or_expired_evidence_cannot_remain_ready(self):
        old=self.service.workspace("sample-one")["preparation"]
        row=self.evidence()
        current=self.service.workspace("sample-one")["preparation"]
        self.assertNotEqual(old["source_hash"],current["source_hash"])
        self.assertEqual(current["outputs"][1]["status"],"PREPARED")
        self.store.save_record("sample-one",{"id":row["id"],"version":row["version"],"kind":"readiness",
            "title":row["title"],"source":"Synthetic failure",
            "data":dict(row["data"],result="FAIL",p0_count=1)})
        failed=self.service.workspace("sample-one")["preparation"]
        self.assertEqual(failed["outputs"][1]["status"],"BLOCKED")
        self.assertNotEqual(failed["source_hash"],current["source_hash"])
        app=self.store.app("sample-one")
        with patch("mission_control.pipeline.iso_time",return_value=__import__("datetime").datetime(2020,1,1,tzinfo=__import__("datetime").timezone.utc)):
            expired=prepare(app,[row])
        self.assertEqual(expired["outputs"][1]["status"],"BLOCKED")
        self.assertNotEqual(expired["source_hash"],prepare(app,[row])["source_hash"])

    def test_cross_app_rejection_and_isolated_manifest_change(self):
        row=self.evidence()
        with self.assertRaises(Invalid):
            prepare(self.store.app("sample-two"),[row])
        with self.assertRaises(Invalid):
            prepare(self.store.app("sample-one"),[],[{"cohort":{"app_id":"sample-two"}}])
        a=self.service.workspace("sample-one")["preparation"]
        b=self.service.workspace("sample-two")["preparation"]
        self.assertNotEqual(a["source_hash"],b["source_hash"])
        self.assertFalse(any(row["hash"] in o["packet"]["source_hashes"] for o in b["outputs"]))
        app=self.store.app("sample-one")
        self.store.save_app("sample-one",dict(app["data"],release="new-build"),app["version"])
        self.assertNotEqual(a["source_hash"],self.service.workspace("sample-one")["preparation"]["source_hash"])
        self.assertEqual(b["source_hash"],self.service.workspace("sample-two")["preparation"]["source_hash"])

    def test_bounded_repeated_local_preparation(self):
        row=self.evidence()
        records=[dict(deepcopy(row),id=str(i)) for i in range(20)]
        app=self.store.app("sample-one")
        start=time.perf_counter()
        for _ in range(100):
            result=prepare(app,records)
            self.assertEqual(len(result["outputs"]),12)
        elapsed=time.perf_counter()-start
        self.assertLess(elapsed,10)
        print("SYNTHETIC_100_PREPARATIONS_SECONDS="+str(round(elapsed,4)))

    def test_scope_helper_checks_each_collection_before_preparation(self):
        app=self.store.app("sample-one")
        self.assertIsNone(check_scope(app,[],[]))
        check_scope(app,[self.evidence()],[{"cohort":{"app_id":"sample-one"}}])
        with self.assertRaises(Invalid):
            check_scope(app,[{"app_id":"sample-two"}],[])
        with self.assertRaises(Invalid):
            check_scope(app,[],[{"cohort":{"app_id":"sample-two"}}])

    def test_grouped_needs_retains_order_and_does_not_rewrite_original_packets(self):
        outputs=[{"stage":1,"missing":["Add proof","Finish stage 2: Dependency"]},
                 {"stage":3,"missing":["Add proof","Connect project"]}]
        original=deepcopy(outputs)
        self.assertEqual(group_needs(outputs),[
            {"message":"Add proof","stages":[1,3]},
            {"message":"Connect project","stages":[3]}])
        self.assertEqual(outputs,original)
        self.assertEqual(group_needs([]),[])

    def test_source_binding_ignores_input_order_and_packet_clock_but_tracks_readiness(self):
        app=self.store.app("sample-one");row=self.evidence()
        records=[row,dict(row,id="second")]
        outputs=prepare(app,records)["outputs"]
        before=source_binding(app,records,[],outputs)
        changed=deepcopy(outputs)
        changed[0]["packet"]["created_at"]="different-preview-clock"
        self.assertEqual(before,source_binding(app,list(reversed(records)),[],changed))
        changed[0]["status"]="BLOCKED"
        self.assertNotEqual(before,source_binding(app,records,[],changed))
        changed=deepcopy(outputs);changed[0]["missing"].append("Expired source")
        self.assertNotEqual(before,source_binding(app,records,[],changed))


if __name__=="__main__":
    unittest.main()
