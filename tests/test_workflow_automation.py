"""App-specific preparation behavior, trustworthy baselines and transaction isolation."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile, time, unittest
from unittest.mock import patch
from mission_control.common import Invalid, digest, now
from mission_control.store import Store, app_data
from mission_control.service import Service
from mission_control.db import connection
from mission_control.guided_workflow import guide
from mission_control.pipeline import evaluate
from mission_control.workflow_automation import recommend, usable_baseline, destination
from mission_control.automation_policy import preferences, channels, check_manifest_version
from mission_control.experiments import Experiments
from tests.test_guided_workflow import complete_records


class WorkflowAutomationTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/"test.sqlite",seed=False)
        self.app=self.store.save_app("future-app",dict(name="Synthetic future app",job="Rehearse an interview",
            audience="Synthetic job seekers",activation="Complete a rehearsal and saved revision",release="fixture-1",
            locale="en-US",currency="USD",retention="Next interview practice cycle",
            channel_hypotheses=["Permitted tutorial","High-intent pilot"],website="https://example.com"))
        self.at=datetime.now(timezone.utc)

    def build(self,app=None,rows=None,reports=None):
        app=app or self.app;rows=rows or [];reports=reports or []
        return recommend(app,rows,reports,guide(app,rows,evaluate(app,rows,reports),reports),self.at)

    def report(self,**updates):
        cohort={"app_id":self.app["id"],"cohort_id":"synthetic-cohort","release":"fixture-1","locale":"en-US","currency":"USD",
                "starts_at":(self.at-timedelta(days=10)).isoformat(),"ends_at":(self.at-timedelta(days=9)).isoformat(),
                "matures_at":(self.at-timedelta(days=1)).isoformat()}
        row={"cohort":cohort,"as_of":self.at.isoformat(),"source_hash":digest(cohort),"status":"SUPPLIED_RECONCILED",
             "mature":True,"costs_complete":True,"observability":"OBSERVED","installs":100,
             "activation_rate":0.4,"paid_conversion":0.1,"retention_rate":0.2}
        row.update(updates);return row

    def test_automatic_future_app_choices_and_no_invented_proof(self):
        result=self.build();self.assertEqual(result["mode"],"AUTO")
        self.assertEqual(result["metric"]["value"],"activation_rate")
        self.assertEqual(result["channel"]["value"],"Permitted tutorial")
        self.assertEqual(result["channel"]["status"],"UNTESTED_PILOT")
        self.assertEqual(result["cadence"],"Next interview practice cycle")
        self.assertEqual(len(result["choices"]),12)
        self.assertEqual(result["next_action"]["id"],"readiness")
        for fields in result["drafts"].values():
            self.assertFalse(set(fields)&{"result","mature","counts","claim","analysis_at","analysis_date","assignment_source"})
        self.assertNotIn("baseline_rate",result["drafts"]["registered_experiment"])
        self.assertEqual(result["drafts"]["distribution"]["budget_minor"],0)
        self.assertEqual(result["drafts"]["distribution"]["mode"],"MANUAL_HANDOFF")
        self.assertFalse(result["automatic_external_writes"]);self.assertEqual(result["authorized_spend_minor"],0)
        self.assertIn("saved revision",result["drafts"]["experiment"]["hypothesis"])

    def test_explicit_preferences_override_without_optimality_claim(self):
        app=deepcopy(self.app);app["data"].update(growth_mode="SUGGEST",growth_metric="retention_rate",
            growth_cadence="D45 meaningful revision",growth_channels="Tutorial\nSearch\nTutorial",growth_channel="Search")
        r=self.build(app);self.assertEqual(r["mode"],"SUGGEST");self.assertEqual(r["metric"]["value"],"retention_rate")
        self.assertEqual(r["cadence"],"D45 meaningful revision");self.assertEqual(r["channel"]["value"],"Search")
        self.assertEqual(r["channel"]["alternatives"],["Tutorial"])
        self.assertEqual(r["channel"]["basis"],"Explicit operator preference")
        app["data"]["growth_mode"]="OFF";self.assertEqual(self.build(app)["mode"],"OFF")

    def test_invalid_preferences_reject_before_manifest_save(self):
        bad=[{"growth_mode":"publish"},{"growth_mode":[]},{"growth_metric":"clicks"},{"growth_metric":{}},
             {"growth_channels":[]},{"growth_channels":"x"*2401},{"growth_channels":"x"*181},
             {"growth_channels":"\n".join(str(n) for n in range(13))},{"channel_hypotheses":"oops"},
             {"channel_hypotheses":[{}]},{"growth_channel":"Not declared"},{"growth_channel":9},
             {"growth_cadence":"a"*2001},{"growth_cadence":False}]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(Invalid):app_data(dict(self.app["data"],**value))
        self.assertEqual(channels({"growth_channels":"\nA\nA\nB\n"}),["A","B"])

    def test_empty_preferences_do_not_invent_cadence_or_channels(self):
        app=deepcopy(self.app);app["data"].update(growth_channels="",growth_cadence="")
        r=self.build(app);self.assertIsNone(r["channel"]["value"]);self.assertIsNone(r["cadence"])
        self.assertEqual(r["channel"]["status"],"NEEDS_INPUT")
        app["data"].pop("retention");app["data"].pop("growth_cadence")
        self.assertEqual(preferences(app["data"])["cadence"],"")

    def test_exact_current_measured_baseline_and_zero(self):
        report=self.report();r=self.build(reports=[report])
        self.assertEqual(r["drafts"]["registered_experiment"]["baseline_rate"],0.4)
        self.assertEqual(r["baseline"]["status"],"SUPPLIED_OBSERVATION")
        report["activation_rate"]=0;zero=self.build(reports=[report])
        self.assertEqual(zero["baseline"]["value"],0)
        self.assertEqual(zero["drafts"]["registered_experiment"]["baseline_rate"],0)
        app=deepcopy(self.app);app["data"]["growth_metric"]="paid_conversion"
        self.assertEqual(self.build(app,reports=[report])["baseline"]["value"],0.1)
        app["data"]["growth_metric"]="retention_rate"
        self.assertEqual(self.build(app,reports=[report])["baseline"]["value"],0.2)

    def test_incomplete_baselines_are_unknown_not_zero(self):
        variants=[{"mature":False},{"costs_complete":False},{"observability":"PARTIAL"},{"status":"INCONCLUSIVE"},
                  {"activation_rate":None},{"activation_rate":True},{"activation_rate":float("inf")},
                  {"activation_rate":-0.01},{"activation_rate":1.01},{"installs":0},
                  {"as_of":(self.at-timedelta(days=31)).isoformat()}, {"as_of":(self.at+timedelta(seconds=1)).isoformat()}]
        for changes in variants:
            with self.subTest(changes=changes):
                result=self.build(reports=[self.report(**changes)])
                self.assertIsNone(result["baseline"]["value"])
                self.assertNotIn("baseline_rate",result["drafts"]["registered_experiment"])

    def test_release_locale_currency_scope_never_borrows_baseline(self):
        for field in ("release","locale","currency"):
            report=self.report();report["cohort"][field]="other"
            self.assertIsNone(self.build(reports=[report])["baseline"]["value"])
            app=deepcopy(self.app);app["data"][field]=""
            self.assertIsNone(self.build(app,reports=[self.report()])["baseline"]["value"])

    def test_latest_inconclusive_wins_over_old_success(self):
        old=self.report();latest=self.report(status="INCONCLUSIVE")
        latest["cohort"]["ends_at"]=(self.at-timedelta(days=2)).isoformat()
        latest["cohort"]["cohort_id"]="newer";latest["source_hash"]=digest(latest["cohort"])
        r=self.build(reports=[old,latest]);self.assertIsNone(r["baseline"]["value"])
        self.assertEqual(r["baseline"]["cohort_id"],"newer")
        self.assertNotEqual(self.build(reports=[old])["source_hash"],r["source_hash"])

    def test_foreign_and_stale_workflows_reject(self):
        g=guide(self.app,[],evaluate(self.app,[]))
        rows=complete_records(self.app);rows[0]["app_id"]="someone-else"
        with self.assertRaises(Invalid):self.build(rows=rows)
        with self.assertRaises(Invalid):recommend(self.app,rows,[],g)
        report=self.report();report["cohort"]["app_id"]="someone-else"
        with self.assertRaises(Invalid):self.build(reports=[report])
        with self.assertRaises(Invalid):recommend(self.app,[],[report],g)
        for key,value in (("app_id","foreign"),("app_version",2)):
            broken=dict(g,**{key:value})
            with self.assertRaises(Invalid):recommend(self.app,[],[],broken)

    def test_hash_binding_updates_and_stays_deterministic(self):
        result=self.build();self.assertEqual(result["source_hash"],self.build()["source_hash"])
        rows=complete_records(self.app);first=self.build(rows=rows);rows[0]["version"]+=1
        self.assertNotEqual(first["source_hash"],self.build(rows=rows)["source_hash"])
        app=deepcopy(self.app);app["version"]+=1
        self.assertNotEqual(result["source_hash"],self.build(app)["source_hash"])
        app["data"]["activation"]="A distinct outcome"
        self.assertIn("A distinct outcome",self.build(app)["drafts"]["experiment"]["hypothesis"])

    def test_latest_failure_retains_authoritative_next_action(self):
        rows=complete_records(self.app);ready=self.build(rows=rows)
        self.assertEqual(ready["next_action"]["id"],"activity")
        failure=deepcopy(rows[0]);failure.update(id="failed",updated="2099-01-01T00:00:00+00:00")
        failure["data"].update(result="FAIL",p0_count=1);failure["hash"]=digest(failure["data"])
        r=self.build(rows=rows+[failure]);self.assertEqual(r["next_action"]["id"],"readiness")
        self.assertEqual(r["choices"][1]["local_status"],"NEEDS_INPUT")
        self.assertNotEqual(ready["source_hash"],r["source_hash"])

    def test_destination_latest_locale_failure_and_unverified_website(self):
        rows=complete_records(self.app);row=next(r for r in rows if r["kind"]=="store")
        row["data"]["destination"]="https://example.com/store"
        result=self.build(rows=rows);self.assertEqual(result["destination"]["value"],"https://example.com/store")
        self.assertEqual(result["destination"]["status"],"OPERATOR_PUBLIC_READBACK")
        failure=deepcopy(row);failure.update(id="failed",updated="2099-01-01T00:00:00+00:00")
        failure["data"]["availability"]="WAITING_FOR_REVIEW"
        self.assertEqual(self.build(rows=rows+[failure])["destination"]["status"],"UNVERIFIED_DRAFT")
        row["data"]["locale"]="fr-FR";self.assertEqual(self.build(rows=rows)["destination"]["value"],self.app["data"]["website"])
        app=deepcopy(self.app);app["data"].pop("website");self.assertIsNone(destination(app,[])["value"])

    def test_versioned_manifest_and_record_rejects_concurrent_change(self):
        prior=self.app["version"];changed=self.store.save_app(self.app["id"],dict(self.app["data"],growth_mode="SUGGEST"),prior)
        body={"kind":"learning","title":"Synthetic draft","source":"Synthetic fixture", "data":{"change":"Draft"},"manifest_version":prior}
        with self.assertRaises(Invalid):self.store.save_record(self.app["id"],body)
        self.assertEqual(self.store.records(self.app["id"]),[])
        body["manifest_version"]=changed["version"];self.store.save_record(self.app["id"],body)
        for bad in (True,0,"2"):
            with self.assertRaises(Invalid):self.store.save_record(self.app["id"],dict(body,manifest_version=bad))
        with connection(self.store.path) as db:
            check_manifest_version(db,self.app["id"],None)
            with self.assertRaises(Invalid):check_manifest_version(db,"absent",1)
        self.assertEqual(Store(self.store.path,seed=False).app(self.app["id"])["data"]["growth_mode"],"SUGGEST")

    def test_registered_experiment_stale_binding_checked_before_plan(self):
        with self.assertRaisesRegex(Invalid,"App setup changed"):
            Experiments(self.store).create(self.app["id"],{"manifest_version":0})
        self.assertEqual(Experiments(self.store).list(self.app["id"]),[])

    def test_read_only_service_packets_and_performance(self):
        def tables():
            with connection(self.store.path) as db:
                return {r[0]:list(map(tuple,db.execute('SELECT * FROM "'+r[0]+'"'))) for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        before=tables()
        with patch("urllib.request.urlopen",side_effect=AssertionError("No network")):
            w=Service(self.store).workspace(self.app["id"])
            self.assertEqual(w["preparation"]["recommendations"],w["automation"])
            self.assertEqual(w["automation"]["next_action"],w["workflow"]["next_action"])
            self.assertEqual(tables(),before)
            rows=complete_records(self.app)*8
            started=time.perf_counter()
            for _ in range(100):self.build(rows=rows)
            elapsed=time.perf_counter()-started;self.assertLess(elapsed,5);print(f"AUTOMATION_100_READS_SECONDS={elapsed:.4f}")

    def test_three_seed_apps_keep_distinct_supplied_cadences(self):
        store=Store(Path(self.folder.name)/"seeds.sqlite")
        # Public examples contain no inherited product hypotheses. Supply three
        # explicitly synthetic policies to prove app-specific choices remain separate.
        for index,identity in enumerate(("sample-one","sample-two","sample-three")):
            app=store.app(identity)
            store.save_app(identity,{**app['data'],
                'retention':f'Synthetic cadence {index}',
                'channel_hypotheses':[f'Synthetic channel {index}'],
                'activation':f'Synthetic useful event {index}'},app['version'])
        results=[Service(store).workspace(identity)["automation"] for identity in ("sample-one","sample-two","sample-three")]
        self.assertEqual(len({r["cadence"] for r in results}),3)
        self.assertEqual(len({r["channel"]["value"] for r in results}),3)
        self.assertEqual(len({r["metric"]["activation"] for r in results}),3)
        self.assertEqual(len({r["source_hash"] for r in results}),3)


if __name__=="__main__":unittest.main()
