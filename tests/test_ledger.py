"""Real SQLite proofs for immutable exports, late refunds and visible uncertainty."""
import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
import time
from mission_control.common import Invalid,digest
from mission_control.ledger import Ledger
from mission_control.store import Store
from mission_control.service import Service
from mission_control.worker import run_once,jobs


def cohort(**changes):
    return dict(dict(cohort_id="pilot-1",release="build-1",platform="iOS",locale="en-US",currency="USD",starts_at="2026-09-01T00:00:00+00:00",ends_at="2026-09-08T00:00:00+00:00",matures_at="2026-10-01T00:00:00+00:00",attribution_method="First-party export",observability="OBSERVED",source="Synthetic permitted export"),**changes)


def event(eid,kind,day="2026-09-02",amount=0,related="",subject="opaque-1",**changes):
    return dict(dict(provider="export",event_id=eid,type=kind,subject_id=subject,occurred_at=day+"T00:00:00+00:00",amount_minor=amount,currency="USD",related_event_id=related,source="Synthetic export receipt"),**changes)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"source/state.sqlite")
        self.service=Service(self.store)
        self.ledger=Ledger(self.store.path)
        self.service.cohort("sample-one",cohort())

    def tearDown(self):
        self.tmp.cleanup()

    def ingest(self,rows):
        return self.service.events("sample-one",{"cohort_id":"pilot-1","events":rows})

    def report(self,as_of="2026-10-11T00:00:00+00:00"):
        return self.ledger.reports("sample-one",as_of)[0]

    def base(self):
        return [event("install","INSTALL"),event("activation","ACTIVATION"),event("purchase","PURCHASE",amount=2000),event("value","VALUE",day="2026-09-20"),event("cost-a","COST_ACQUISITION",amount=300),event("cost-d","COST_DELIVERY",amount=100)]

    def test_reconciled_counts_costs_and_restart(self):
        rows=self.base()+[event("install-duplicate-subject","INSTALL"),event("another-value","VALUE",day="2026-09-21")]
        self.assertEqual(self.ingest(rows)["inserted"],8)
        result=self.report()
        self.assertEqual((result["installs"],result["activated"],result["paid"],result["retained"]),(1,1,1,1))
        self.assertEqual(result["status"],"SUPPLIED_RECONCILED")
        self.assertEqual(result["contribution_after_acquisition_minor"],1600)
        self.assertEqual(result["paid_cac_minor"],300)
        self.assertEqual(Ledger(self.store.path).reports("sample-one","2026-10-11T00:00:00+00:00")[0],result)

    def test_duplicate_conflict_and_atomic_batch(self):
        self.ingest(self.base())
        result=self.ingest(self.base())
        self.assertEqual(result,{"inserted":0,"duplicates":6,"cohort_id":"pilot-1","provenance":"OPERATOR_IMPORT; provider signatures not verified"})
        with self.assertRaisesRegex(Invalid,"different content"):
            self.ingest([event("new","VALUE"),event("purchase","PURCHASE",amount=999)])
        self.assertEqual(len(self.ledger.export("sample-one")["events"]),6)

    def test_late_refund_reversal_and_historical_as_of(self):
        self.ingest(self.base())
        before=self.report("2026-10-02T00:00:00+00:00")
        self.ingest([event("refund","REFUND","2026-10-03",500,"purchase")])
        self.assertEqual(self.report()["contribution_after_acquisition_minor"],1100)
        self.assertEqual(self.report("2026-10-02T00:00:00+00:00"),before)
        self.ingest([event("reverse","REFUND_REVERSED","2026-10-05",500,"refund")])
        self.assertEqual(self.report()["contribution_after_acquisition_minor"],1600)
        self.assertEqual(self.report()["refunds_minor"],0)

    def test_orphan_excessive_and_currency_unknown(self):
        self.ingest(self.base()+[event("orphan","REFUND",amount=500,related="absent")])
        self.assertIsNone(self.report()["net_proceeds_minor"])
        self.assertEqual(self.report()["status"],"INCONCLUSIVE")
        self.ingest([event("absent","PURCHASE",amount=500)])
        self.assertEqual(self.report()["net_proceeds_minor"],2000)
        self.ingest([event("excess","REFUND",amount=9999,related="purchase")])
        self.assertIsNone(self.report()["net_proceeds_minor"])
        self.assertTrue(self.report()["issues"])

    def test_partial_immature_zero_and_missing_costs(self):
        self.ingest([event("install","INSTALL"),event("purchase","PURCHASE",amount=2000)])
        self.assertFalse(self.report()["costs_complete"])
        self.assertIsNone(self.report()["contribution_after_acquisition_minor"])
        self.ingest([event("cost-a","COST_ACQUISITION"),event("cost-d","COST_DELIVERY")])
        self.assertIsNone(self.report("2026-09-20T00:00:00+00:00")["paid_conversion"])
        self.service.cohort("sample-one",cohort(cohort_id="partial",observability="PARTIAL"))
        self.service.events("sample-one",{"cohort_id":"partial","events":[event("p-install","INSTALL"),event("p-a","COST_ACQUISITION"),event("p-d","COST_DELIVERY")]})
        partial=next(r for r in self.ledger.reports("sample-one") if r["cohort"]["cohort_id"]=="partial")
        self.assertEqual(partial["status"],"INCONCLUSIVE")
        self.assertIsNone(partial["paid_conversion"])

    def test_input_and_cross_app_boundaries(self):
        for row in (event("bad","INSTALL",subject="test@example.com"),event("bad","PURCHASE",amount=True),dict(event("bad","INSTALL"),email="private@example.com"),event("bad","PURCHASE",currency="usd"),event("future","INSTALL",day="2999-01-01")):
            with self.subTest(row=row),self.assertRaises(Invalid):self.ingest([row])
        self.assertEqual(self.ledger.export("sample-one")["events"],[])
        with self.assertRaises(Invalid):self.service.events("sample-two",{"cohort_id":"pilot-1","events":self.base()})
        self.service.cohort("sample-two",cohort())
        self.service.events("sample-two",{"cohort_id":"pilot-1","events":self.base()})
        self.assertEqual(len(self.ledger.export("sample-one")["events"]),0)
        self.assertEqual(len(self.ledger.export("sample-two")["events"]),6)
        with self.assertRaisesRegex(Invalid,"definition changed"):
            self.service.cohort("sample-one",cohort(currency="EUR"))

    def test_csv_and_snapshot_integrity(self):
        row=event("install","INSTALL")
        header=",".join(row)
        values=",".join(str(v) for v in row.values())
        result=self.service.events("sample-one",{"cohort_id":"pilot-1","csv":header+"\n"+values})
        self.assertEqual(result["inserted"],1)
        snapshot=self.store.export("sample-one")
        restored=Store(Path(self.tmp.name)/"restored/state.sqlite",seed=False)
        restored.restore(snapshot)
        self.assertEqual(Ledger(restored.path).export("sample-one"),self.ledger.export("sample-one"))
        bad=copy.deepcopy(snapshot)
        bad["payload"]["ledger"]["events"][0]["data"]["event_id"]="changed"
        bad["sha256"]=digest(bad["payload"])
        empty=Store(Path(self.tmp.name)/"bad/state.sqlite",seed=False)
        with self.assertRaisesRegex(Invalid,"event hash"):
            empty.restore(bad)
        self.assertEqual(empty.apps(),[])

    def test_mixed_currency_excessive_reversal_and_duplicate_headers(self):
        self.ingest(self.base()+[event("foreign","COST_DELIVERY",amount=100,currency="EUR")])
        self.assertIsNone(self.report()["net_proceeds_minor"])
        self.assertIn("Mixed currencies",self.report()["issues"][0])
        with self.assertRaises(Invalid):
            self.service.events("sample-one",{"cohort_id":"pilot-1","csv":"provider,provider\nexport,other"})
        self.assertEqual(len(self.ledger.export("sample-one")["events"]),7)
        with self.assertRaisesRegex(Invalid,"future"):
            self.report("2999-01-01T00:00:00+00:00")
        self.service.cohort("sample-two",cohort())
        rows=self.base()+[event("refund","REFUND",amount=500,related="purchase"),event("reverse","REFUND_REVERSED",amount=501,related="refund")]
        self.service.events("sample-two",{"cohort_id":"pilot-1","events":rows})
        result=self.ledger.reports("sample-two")[0]
        self.assertIsNone(result["net_proceeds_minor"])
        self.assertTrue(result["issues"])

    def test_workflow_uses_current_ledger_and_hashes(self):
        original=self.store.app("sample-one")
        self.store.save_app("sample-one",dict(original["data"],release="build-1",job="Synthetic job",audience="Synthetic audience",activation="Synthetic useful result",locale="en-US"),original["version"])
        self.service.evidence("sample-one",{"kind":"measurement","title":"Synthetic measurement","source":"Synthetic contract","data":{"release":"build-1","result":"PASS","attribution_method":"export","consent_review":True,"refund_reconciliation":True}})
        self.ingest(self.base())
        workspace=self.service.workspace("sample-one")
        self.assertEqual(workspace["stages"][3]["status"],"READY")
        self.service.queue("sample-one",{"action":"pipeline","data":{"stage":4},"request_key":"ledger-workflow"})
        run_once(self.store)
        packet=jobs(self.store,"sample-one")[0]["result"]["outputs"][0]["packet"]
        self.assertEqual(packet["content"]["event_ledger"][0]["contribution_after_acquisition_minor"],1600)
        self.assertIn(workspace["ledger"][0]["source_hash"],packet["source_hashes"])
        self.service.cohort("sample-one",cohort(cohort_id="later",ends_at="2026-09-10T00:00:00+00:00"))
        self.assertEqual(self.service.workspace("sample-one")["stages"][3]["status"],"BLOCKED")

    def test_bounded_batch_and_local_report_time(self):
        rows=[event("install-"+str(i),"INSTALL",subject="opaque-"+str(i)) for i in range(500)]
        self.ingest(rows)
        with self.assertRaises(Invalid):self.ingest(rows+[event("extra","INSTALL")])
        started=time.perf_counter()
        for _ in range(10):self.assertEqual(self.report()["installs"],500)
        self.assertLess(time.perf_counter()-started,10)


if __name__=="__main__":unittest.main()
