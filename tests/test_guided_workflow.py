"""Actual current stage behavior, isolation and side-effect-free operator guidance."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from pathlib import Path
import tempfile,time,unittest
from unittest.mock import patch
from mission_control.common import Invalid,now,digest
from mission_control.db import connection
from mission_control.guided_workflow import guide,tool,primary,step,TOOLS,STEP_TOOLS
from mission_control.pipeline import evaluate,current
from mission_control.packets import creative
from mission_control.service import Service
from mission_control.store import Store


def complete_records(app):
    """Explicit supplied synthetic stage inputs; no actual product/provider claim."""
    kinds=["readiness","measurement","cohort","claim","asset","store","experiment","distribution","route","billing","retention","evaluation","learning"]
    data={"release":app["data"]["release"],"locale":app["data"]["locale"],"result":"PASS","p0_count":0,"checked_at":now(),
          "consent_review":True,"refund_reconciliation":True,"authentic":True,"rights_cleared":True,
          "file_id":"synthetic.png","availability":"AVAILABLE","mature":True,
          "installed":True,"fresh_install":True,"signed_out":True,"restore_tested":True,"trial_eligibility_tested":True}
    from tests.journey_fixtures import covered
    data.update(covered(app['data']['release'],app['data']['locale']))
    return [{"id":kind,"app_id":app["id"],"kind":kind,"title":"Synthetic "+kind,"data":deepcopy(data),
             "version":1,"hash":digest({"kind":kind,"data":data}),"updated":now()} for kind in kinds]


class GuidedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/"test.sqlite",seed=False)
        self.app=self.store.save_app("sample-one",dict(name="Synthetic app",release="synthetic-build",job="Synthetic job",audience="Synthetic audience",activation="Synthetic value",locale="en-US"))

    def build(self,rows=None,app=None):
        rows=[] if rows is None else rows;app=app or self.app
        return guide(app,rows,evaluate(app,rows))

    def test_direct_next_input_and_all_fixed_tools(self):
        g=self.build();self.assertEqual(g["next_step"],2);self.assertEqual(g["next_action"]["id"],"readiness")
        self.assertEqual(len(g["steps"]),12);self.assertEqual(g["local_ready_count"],1)
        self.assertEqual({r["id"] for s in g["steps"] for r in s["tools"]},set(TOOLS)-{"findings"})
        self.assertEqual(g["steps"][2]["primary"]["id"],"measurement")
        self.assertTrue(g["steps"][4]["dependency_needs"])
        self.assertEqual(set(STEP_TOOLS),set(range(1,13)))
        self.assertEqual(tool("upload")["route"],"upload")

    def test_all_local_ready_is_never_execution_or_success(self):
        g=self.build(complete_records(self.app))
        self.assertEqual(g["local_ready_count"],12);self.assertIsNone(g["next_step"])
        self.assertEqual(g["next_action"]["id"],"activity")
        self.assertEqual(g["classification"],"LOCAL_GUIDANCE_NOT_RELEASE_APPROVAL")
        self.assertFalse(g["automatic_external_writes"]);self.assertEqual(g["authorized_spend_minor"],0)
        self.assertNotIn("COMPLETE",g.values());self.assertEqual(g["outcomes"],"INSPECT_MATURE_SOURCE_REPORTS")

    def test_latest_failure_release_and_critical_finding_recovery(self):
        rows=complete_records(self.app);ready=self.build(rows)
        failure=deepcopy(rows[0]);failure.update(id="new-failure",updated="2099-01-01T00:00:00+00:00")
        failure["data"].update(result="FAIL",p0_count=1);failure["hash"]=digest(failure["data"])
        g=self.build(rows+[failure]);self.assertEqual(g["next_action"]["id"],"readiness")
        self.assertNotEqual(ready["source_hash"],g["source_hash"])
        changed=deepcopy(self.app);changed["data"]["release"]="next-build";changed["version"]+=1
        self.assertEqual(self.build(rows,changed)["next_step"],2)
        finding=dict(failure,id="review",kind="review",title="Synthetic P0",data={"confirmed":True,"severity":"P0"})
        g=self.build(rows+[finding]);self.assertEqual(g["next_step"],5);self.assertEqual(g["next_action"]["id"],"findings")
        self.assertEqual(g["steps"][4]["critical_findings"],["Synthetic P0"])

    def test_manifest_and_direct_asset_repair(self):
        app=deepcopy(self.app);app["data"]["job"]=""
        self.assertEqual(self.build(app=app)["next_action"]["id"],"app")
        rows=[r for r in complete_records(self.app) if r["kind"]!="asset"]
        g=self.build(rows);self.assertEqual(g["next_action"]["id"],"upload")
        stage=evaluate(self.app,[])[3]
        self.assertEqual(primary(stage,["Reconcile the latest event cohort"],[])["id"],"results")

    def test_foreign_or_malformed_context_rejects(self):
        rows=complete_records(self.app);rows[0]["app_id"]="sample-two"
        with self.assertRaises(Invalid):self.build(rows)
        for malformed in ([],list(reversed(evaluate(self.app,[]))),[{}]*12):
            with self.assertRaises(Invalid):guide(self.app,[],malformed)
        with self.assertRaises(Invalid):guide(self.app,[],evaluate(self.app,[]),[{"cohort":{"app_id":"sample-two"}}])

    def test_stable_source_hash_and_record_version_binding(self):
        rows=complete_records(self.app);first=self.build(rows)
        self.assertEqual(first["source_hash"],self.build(rows)["source_hash"])
        rows[0]["version"]+=1
        self.assertNotEqual(first["source_hash"],self.build(rows)["source_hash"])
        foreign=deepcopy(self.app);foreign["id"]="other"
        self.assertNotEqual(self.build()["source_hash"],self.build(app=foreign)["source_hash"])

    def test_saved_read_only_service_and_performance(self):
        def inventory():
            with connection(self.store.path) as db:
                return {r[0]:db.execute('SELECT count(*) FROM "'+r[0]+'"').fetchone()[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        before=inventory()
        with patch("urllib.request.urlopen",side_effect=AssertionError("No network")):
            first=Service(self.store).workspace("sample-one")["workflow"]
            second=Service(Store(self.store.path,seed=False)).workspace("sample-one")["workflow"]
        self.assertEqual(before,inventory());self.assertEqual(first,second)
        rows=complete_records(self.app)
        rows += [dict(rows[0],id="fixture-"+str(i)) for i in range(87)]
        start=time.monotonic();self.build(rows);self.assertLess(time.monotonic()-start,5)

    def test_expired_readiness_cannot_keep_saved_checklist_ready(self):
        rows=complete_records(self.app);old=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
        rows[0]["data"]["checked_at"]=old;rows[0]["hash"]=digest(rows[0]["data"])
        self.assertEqual(self.build(rows)["next_action"]["id"],"readiness")

    def test_locale_readiness_missing_foreign_and_release_change(self):
        for kind in ("claim","asset","store"):
            for locale in (None,"fr-FR"):
                rows=complete_records(self.app);row=next(r for r in rows if r["kind"]==kind)
                row["data"]["locale"]=locale
                self.assertFalse(current(row,self.app))
                g=self.build(rows);self.assertEqual(g["steps"][4]["local_status"],"NEEDS_INPUT")
                self.assertEqual(g["next_action"]["id"],"upload" if kind=="asset" else kind)
        changed=deepcopy(self.app);changed["data"]["locale"]="fr-FR";changed["version"]+=1
        self.assertNotEqual(self.build()["source_hash"],self.build(app=changed)["source_hash"])
        self.assertEqual(self.build(complete_records(self.app),changed)["next_step"],2)

    def test_latest_result_stays_within_exact_locale(self):
        rows=complete_records(self.app)
        foreign=deepcopy(next(r for r in rows if r["kind"]=="claim"))
        foreign.update(id="foreign-latest",updated="2099-01-01T00:00:00+00:00")
        foreign["data"].update(locale="fr-FR",result="FAIL")
        self.assertEqual(self.build(rows+[foreign])["steps"][4]["local_status"],"LOCAL_INPUTS_READY")
        next(r for r in rows if r["kind"]=="claim")["data"]["result"]="FAIL"
        foreign["data"]["result"]="PASS"
        self.assertEqual(self.build(rows+[foreign])["steps"][4]["local_status"],"NEEDS_INPUT")

    def test_creative_promise_cannot_come_from_foreign_locale(self):
        row=next(r for r in complete_records(self.app) if r["kind"]=="claim")
        row["data"]["claim"]="Current locale proof"
        foreign=deepcopy(row);foreign["data"].update(locale="fr-FR",claim="Foreign promise")
        self.assertTrue(all(b["promise"]=="Current locale proof" for b in creative(self.app,[foreign,row])))
        foreign["data"].pop("locale")
        self.assertTrue(all(b["promise"]==self.app["data"]["job"] for b in creative(self.app,[foreign])))


if __name__=="__main__":unittest.main()
