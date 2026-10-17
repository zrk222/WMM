"""Real adapter/state/HTTP behavior with synthetic provider bytes and isolated databases."""
import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from mission_control.common import Invalid, canonical
from mission_control.db import connection
from mission_control.store import Store
from mission_control.insights import Insights
from mission_control import insights_contract as contract
from mission_control import insights_transport as transport
from mission_control.credential_vault import Vault


def setup_body(provider="posthog", automatic=False):
    return dict(provider=provider,project_id={"posthog":"123","clarity":"abcdef","revenuecat":"projabc"}[provider],
                region="us" if provider=="posthog" else "global",
                api_key={"posthog":"phx_"+"A"*24,"clarity":"eyJhbGciOiJIUzI1NiJ9.eyJwcm9qZWN0IjoiYWJjZGVmIn0."+("S"*24),"revenuecat":"sk_"+"B"*24}[provider],
                automatic=automatic,confirm_read=True,dedicated_project=True)


def payloads():
    return {"posthog":[{"id":123},{"results":[["signup_completed",12],["activation_completed",5]]}],
            "clarity":[[{"metricName":"Traffic","information":[{"totalSessionCount":"12","privateUrl":"https://private.test/person","PagesPerSessionPercentage":1.5}]}]],
            "revenuecat":[{"object":"overview_metrics","currency":"USD","metrics":[{"id":"active_trials","name":"Active Trials","unit":"customers","period":"P0D","value":2,"last_updated_at":1700000000000}]}]}


class FakeVault:
    values={}
    fail_delete=0
    def put(self,name,value):self.values[name]=copy.deepcopy(value)
    def get(self,name):return copy.deepcopy(self.values.get(name))
    def delete(self,name):
        if type(self).fail_delete:
            type(self).fail_delete-=1
            raise Invalid("synthetic native cleanup failure")
        self.values.pop(name,None)


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.temp.name)/"test.sqlite3")
        self.insights=Insights(self.store)
        FakeVault.values={}
        FakeVault.fail_delete=0
        self.vault=patch("mission_control.insights.Vault",FakeVault);self.vault.start()
        self.addCleanup(self.vault.stop);self.addCleanup(self.temp.cleanup)

    def create(self,provider="posthog",automatic=False):
        with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()[provider])):
            return self.insights.setup("sample-one",setup_body(provider,automatic))

    def test_all_three_save_and_automatically_read_with_sanitized_shapes(self):
        for provider in contract.PROVIDERS:
            result=self.create(provider)
            self.assertEqual(result["read"]["status"],"CONNECTED")
        w=self.insights.list("sample-one");self.assertEqual(len(w["reports"]),3)
        self.assertNotIn("private.test",json.dumps(w))
        self.assertNotIn("privateUrl",json.dumps(w))
        for provider in contract.PROVIDERS:
            self.assertNotIn(setup_body(provider)["api_key"],json.dumps(w))
        self.assertEqual(self.insights.list("sample-two")["sources"],[])
        self.assertEqual(len(self.store.export("sample-one")["payload"]["records"]),0)
        self.assertEqual(w["reports"][0]["data"]["rows"][0]["unit"],"customers")

    def test_config_project_scope_validate_key_reject_public_sdk_and_untrusted_fields(self):
        for changes in ({"api_key":"phc_"+"X"*24},{"project_id":"123/../../evil"},{"region":"https://evil.test"},
                        {"dedicated_project":False},{"confirm_read":False},{"automatic":"true"},{"unexpected":"field"}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):
                contract.config({**setup_body(),**changes})
        with self.assertRaises(Invalid):contract.config(setup_body("revenuecat")|{"api_key":"appl_"+"A"*24})
        with self.assertRaises(Invalid):contract.validate_key("clarity","not-an-export-token")
        with self.assertRaises(Invalid):contract.project_scope(setup_body()|{"project_id":True})

    def test_shapes_finite_text_numeric_strings_and_missing_are_not_zero(self):
        self.assertFalse(contract.finite(float("nan")));self.assertFalse(contract.finite(True))
        with self.assertRaises(Invalid):contract.text("x"*201)
        with self.assertRaises(Invalid):contract.shape_revenuecat([])
        with self.assertRaises(Invalid):contract.shape_revenuecat({"object":"overview_metrics","metrics":[{"value":None}]})
        self.assertEqual(contract.numeric_strings({"total":"1.5","email":"123","totalSessionCount":"bad"}),{"total":1.5})
        self.assertEqual(contract.shape_posthog({"results":[]}),[])
        with self.assertRaises(Invalid):contract.shape_posthog({"results":[["someone@email.test",1]]})
        with self.assertRaises(Invalid):contract.validate_event_count(["signup_completed",-1])
        with self.assertRaises(Invalid):contract.shape_posthog({"results":[],"query_status":{"complete":False}})
        self.assertEqual(contract.shape_posthog({"results":[],"query_status":{"complete":True}}),[])
        self.assertEqual(contract.shape_clarity([{"metricName":"PopularPages","information":[{"url":"private"}]}]),[])
        with self.assertRaises(Invalid):contract.clarity_rows({"information":[True]})

    def test_cross_app_project_reuse_and_wrong_app_source_are_rejected(self):
        result=self.create()
        with self.assertRaises(Invalid):self.insights.setup("sample-two",setup_body())
        with self.assertRaises(KeyError):self.insights.refresh("sample-two",result["source_id"],{"confirm_read":True})

    def test_rotation_version_and_prior_key_retirement(self):
        result=self.create();sid=result["source_id"];old=list(FakeVault.values)
        with self.assertRaises(Invalid):self.insights.setup("sample-one",setup_body())
        with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])):
            rotated=self.insights.setup("sample-one",{**setup_body(),"version":1})
        self.assertEqual(rotated["source_id"],sid)
        self.assertNotIn(old[0],FakeVault.values)
        self.assertEqual(self.insights.list("sample-one")["sources"][0]["version"],2)

    def test_failed_rotation_preserves_binding_schedule_status_and_reports(self):
        result=self.create("posthog",True);sid=result["source_id"]
        with connection(self.store.path) as db:
            db.execute("UPDATE insight_sources SET next_due=?,last_error=? WHERE app_id=? AND id=?",(1893456000,"previous safe state","sample-one",sid))
            before=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            reports=[dict(row) for row in db.execute("SELECT * FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid",("sample-one",sid))]
        old_secret=before["credential_ref"]
        replacement={**setup_body("posthog",False),"api_key":"phx_"+"Z"*24,"version":before["version"]}
        with patch("mission_control.insights_transport.request",side_effect=transport.ProviderFailure("PERMISSION_REQUIRED","Provider HTTP 403; check token")):
            with self.assertRaises(Invalid) as caught:self.insights.setup("sample-one",replacement)
        self.assertIn("Replacement not activated",str(caught.exception))
        self.assertNotIn(replacement["api_key"],str(caught.exception))
        with connection(self.store.path) as db:
            after=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            reports_after=[dict(row) for row in db.execute("SELECT * FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid",("sample-one",sid))]
            cleanup=db.execute("SELECT COUNT(*) FROM insight_cleanup WHERE app_id=? AND source_id=?",("sample-one",sid)).fetchone()[0]
        self.assertEqual(after,before)
        self.assertEqual(reports_after,reports)
        self.assertEqual(cleanup,0)
        self.assertIn(self.insights.name("sample-one",old_secret),FakeVault.values)
        self.assertEqual(len(FakeVault.values),1)

    def test_failed_commit_rolls_back_source_and_report_before_candidate_cleanup(self):
        original=self.create("posthog",True);sid=original["source_id"]
        with connection(self.store.path) as db:
            before=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            reports=[dict(row) for row in db.execute("SELECT * FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid",("sample-one",sid))]
        replacement={**setup_body(),"api_key":"phx_"+"Y"*24,"version":before["version"]}
        with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])),patch.object(self.insights,"report",side_effect=RuntimeError("synthetic report persistence failure")):
            with self.assertRaises(Invalid) as caught:self.insights.setup("sample-one",replacement)
        self.assertIn("Replacement not activated",str(caught.exception))
        with connection(self.store.path) as db:
            after=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            reports_after=[dict(row) for row in db.execute("SELECT * FROM insight_reports WHERE app_id=? AND source_id=? ORDER BY rowid",("sample-one",sid))]
        self.assertEqual(after,before)
        self.assertEqual(reports_after,reports)
        self.assertEqual(len(FakeVault.values),1)
        self.assertEqual(next(iter(FakeVault.values.values()))["api_key"],setup_body()["api_key"])

    def test_failed_initial_setup_leaves_no_source_or_candidate(self):
        body=setup_body();secret=body["api_key"]
        with patch("mission_control.insights_transport.request",side_effect=transport.ProviderFailure("PERMISSION_REQUIRED","Provider HTTP 403; check token")):
            with self.assertRaises(Invalid) as caught:self.insights.setup("sample-one",body)
        self.assertIn("SOURCE_NOT_SAVED",str(caught.exception))
        self.assertIn("Enter the key again to retry",str(caught.exception))
        self.assertNotIn(secret,str(caught.exception))
        self.assertEqual(self.insights.list("sample-one")["sources"],[])
        self.assertEqual(FakeVault.values,{})
        with connection(self.store.path) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM insight_cleanup").fetchone()[0],0)

    def test_failed_candidate_cleanup_is_journaled_then_retried_before_next_rotation(self):
        original=self.create("posthog",True);sid=original["source_id"]
        before=self.insights.list("sample-one")["sources"][0]
        with connection(self.store.path) as db:old_ref=db.execute("SELECT credential_ref FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone()[0]
        failed={**setup_body(),"api_key":"phx_"+"Z"*24,"version":before["version"]}
        FakeVault.fail_delete=1
        with patch("mission_control.insights_transport.request",side_effect=transport.ProviderFailure("NETWORK_ERROR","retry")):
            with self.assertRaises(Invalid) as caught:self.insights.setup("sample-one",failed)
        self.assertIn("cleanup is recorded",str(caught.exception))
        with connection(self.store.path) as db:
            stable=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            cleanup=db.execute("SELECT credential_ref FROM insight_cleanup WHERE app_id=? AND source_id=?",("sample-one",sid)).fetchall()
        self.assertEqual(stable["version"],before["version"])
        self.assertEqual(stable["credential_ref"],old_ref)
        self.assertEqual(len(cleanup),1)
        failed_ref=cleanup[0][0]
        self.assertIn(self.insights.name("sample-one",failed_ref),FakeVault.values)
        replacement={**setup_body(),"api_key":"phx_"+"Y"*24,"version":before["version"]}
        with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])):
            rotated=self.insights.setup("sample-one",replacement)
        self.assertEqual(rotated["read"]["status"],"CONNECTED")
        self.assertNotIn(self.insights.name("sample-one",failed_ref),FakeVault.values)
        self.assertNotIn(self.insights.name("sample-one",stable["credential_ref"]),FakeVault.values)
        with connection(self.store.path) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM insight_cleanup WHERE app_id=?",("sample-one",)).fetchone()[0],0)

    def test_stale_candidate_loses_rotation_race_and_keeps_winner(self):
        original=self.create();sid=original["source_id"]
        first={**setup_body(),"api_key":"phx_"+"Y"*24,"version":1}
        second={**setup_body(),"api_key":"phx_"+"Z"*24,"version":1}
        winner=[]
        def racing_request(url,token,body=None):
            if token==second["api_key"] and body is None and not winner:
                with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])):
                    winner.append(self.insights.setup("sample-one",first))
                return {"id":123}
            if token==second["api_key"]:
                return {"results":[]}
            raise AssertionError("unexpected candidate token")
        with patch("mission_control.insights_transport.request",side_effect=racing_request):
            with self.assertRaises(Invalid) as caught:self.insights.setup("sample-one",second)
        self.assertIn("Replacement not activated",str(caught.exception))
        self.assertEqual(len(winner),1)
        with connection(self.store.path) as db:
            row=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            report_count=db.execute("SELECT COUNT(*) FROM insight_reports WHERE app_id=? AND source_id=?",("sample-one",sid)).fetchone()[0]
        self.assertEqual(row["version"],2)
        self.assertIn(self.insights.name("sample-one",row["credential_ref"]),FakeVault.values)
        self.assertEqual(report_count,2)
        self.assertEqual(len(FakeVault.values),1)
        self.assertEqual(next(iter(FakeVault.values.values()))["api_key"],first["api_key"])

    def test_candidate_provider_read_holds_no_sqlite_transaction(self):
        body=setup_body()
        def unlocked_read(data,token):
            db=sqlite3.connect(self.store.path,timeout=.2)
            try:
                db.execute("BEGIN IMMEDIATE")
                db.rollback()
            finally:
                db.close()
            with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])):
                return transport.read(data,token)
        with patch("mission_control.insights.read",side_effect=unlocked_read):
            result=self.insights.setup("sample-one",body)
        self.assertEqual(result["read"]["status"],"CONNECTED")

    def test_disconnect_during_candidate_read_prevents_stale_reactivation(self):
        original=self.create();sid=original["source_id"]
        body={**setup_body(),"api_key":"phx_"+"Z"*24,"version":1}
        disconnected=[]
        def disconnect_during_read(url,token,query=None):
            if query is None and not disconnected:
                disconnected.append(self.insights.disconnect("sample-one",sid,{"version":1,"confirm_disconnect":True}))
                return {"id":123}
            return {"results":[]}
        with patch("mission_control.insights_transport.request",side_effect=disconnect_during_read):
            with self.assertRaises(Invalid) as caught:self.insights.setup("sample-one",body)
        self.assertIn("Replacement not activated",str(caught.exception))
        self.assertEqual(disconnected[0]["status"],"DISCONNECTED")
        with connection(self.store.path) as db:
            source=dict(db.execute("SELECT * FROM insight_sources WHERE app_id=? AND id=?",("sample-one",sid)).fetchone())
            reports=db.execute("SELECT COUNT(*) FROM insight_reports WHERE app_id=? AND source_id=?",("sample-one",sid)).fetchone()[0]
        self.assertEqual(source["status"],"DISCONNECTED")
        self.assertEqual(source["version"],2)
        self.assertEqual(reports,1)
        self.assertEqual(FakeVault.values,{})

    def test_failed_clarity_candidate_reads_consume_existing_rolling_quota(self):
        body=setup_body("clarity");failure=transport.ProviderFailure("NETWORK_ERROR","retry")
        with patch("mission_control.insights_transport.request",side_effect=failure) as mocked:
            for _ in range(10):
                with self.assertRaises(Invalid):self.insights.setup("sample-one",body)
            self.assertEqual(mocked.call_count,10)
            with self.assertRaises(Invalid):self.insights.setup("sample-one",body)
            self.assertEqual(mocked.call_count,10)
        with connection(self.store.path) as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM insight_requests").fetchone()[0],10)
        self.assertEqual(FakeVault.values,{})

    def test_disconnect_cancels_future_reads_and_preserves_report(self):
        sid=self.create(automatic=True)["source_id"]
        self.assertEqual(self.insights.disconnect("sample-one",sid,{"version":1,"confirm_disconnect":True})["status"],"DISCONNECTED")
        self.assertEqual(FakeVault.values,{})
        self.assertEqual(len(self.insights.list("sample-one")["reports"]),1)
        with self.assertRaises(Invalid):self.insights.refresh("sample-one",sid,{"confirm_read":True})
        self.assertEqual(self.insights.tick()["status"],"IDLE")

    def test_failure_keeps_last_good_report_and_permission_pauses_schedule(self):
        sid=self.create(automatic=True)["source_id"]
        with patch("mission_control.insights.read",side_effect=transport.ProviderFailure("PERMISSION_REQUIRED","Provider HTTP 403; reconnect")):
            result=self.insights.refresh("sample-one",sid,{"confirm_read":True})
        self.assertEqual(result["status"],"PERMISSION_REQUIRED")
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET next_due=0")
        with patch("mission_control.insights.read") as mocked:self.assertEqual(self.insights.tick()["status"],"IDLE");mocked.assert_not_called()
        self.assertEqual(len(self.insights.list("sample-one")["reports"]),1)

    def test_scheduler_runs_only_opted_in_due_source_and_not_twice(self):
        self.create("posthog",False);self.create("clarity",True)
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET next_due=0")
        with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["clarity"])) as mocked:
            self.assertEqual(self.insights.tick()["status"],"CONNECTED");self.assertEqual(mocked.call_count,1)
            self.assertEqual(self.insights.tick()["status"],"IDLE")

    def test_clarity_rolling_cap_counts_failure_and_rotation_and_reserves_atomically(self):
        sid=self.create("clarity",True)["source_id"]
        with patch("mission_control.insights.read",side_effect=transport.ProviderFailure("NETWORK_ERROR","retry")):
            for _ in range(9):self.insights.refresh("sample-one",sid,{"confirm_read":True})
            with self.assertRaises(transport.ProviderFailure):self.insights.refresh("sample-one",sid,{"confirm_read":True})
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET next_due=0")
        self.insights.tick()
        self.assertEqual(self.insights.list("sample-one")["sources"][0]["status"],"LOCAL_RATE_LIMITED")

    def test_lease_and_late_result_reject_after_disconnect_or_replacement(self):
        sid=self.create()["source_id"];row=self.insights.reserve("sample-one",sid,False)
        with self.assertRaises(Invalid):self.insights.reserve("sample-one",sid,False)
        self.insights.disconnect("sample-one",sid,{"version":1,"confirm_disconnect":True})
        self.assertEqual(self.insights.complete("sample-one",row,{}, "CONNECTED",None)["status"],"OBSOLETE_RESULT_DISCARDED")
        self.assertEqual(self.insights.list("sample-one")["sources"][0]["status"],"DISCONNECTED")

    def test_configuration_and_report_tampering_fail_closed(self):
        self.create()
        with connection(self.store.path) as db:db.execute("UPDATE insight_reports SET data='{}'")
        with self.assertRaises(Invalid):self.insights.list("sample-one")
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET data='{}'")
        with self.assertRaises(Invalid):self.insights.list("sample-one")

    def test_native_vault_roundtrip_isolated_then_removed(self):
        name="AppGrowthInsights/native-test-"+self.temp.name.replace("\\","/").split("/")[-1]
        vault=Vault()
        try:
            vault.put(name,{"api_key":"synthetic-not-a-provider-token"})
            self.assertEqual(vault.get(name)["api_key"],"synthetic-not-a-provider-token")
        finally:vault.delete(name)
        self.assertIsNone(vault.get(name))

    def test_transport_exact_fixed_hosts_queries_region_and_scope(self):
        for provider in contract.PROVIDERS:
            with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()[provider])) as request:
                result=transport.read(contract.config(setup_body(provider)),setup_body(provider)["api_key"])
                self.assertEqual(result["provider"],provider)
                self.assertIn("PROJECT",result["scope"])
                if provider=="posthog":
                    self.assertEqual(request.call_args[0][0],"https://us.posthog.com/api/projects/123/query/")
                    self.assertIn("GROUP BY event",request.call_args[0][2]["query"]["query"])
                if provider=="clarity":self.assertIn("?numOfDays=3",request.call_args[0][0])
                if provider=="revenuecat":self.assertTrue(request.call_args[0][0].endswith("/projabc/metrics/overview"))
        with patch("mission_control.insights_transport.request",side_effect=[{"id":999},{"results":[]}]) as request:
            with self.assertRaises(Invalid):transport.read(contract.config(setup_body()),"synthetic")
            self.assertEqual(request.call_count,1)

    def test_real_http_adapter_method_authorization_caps_and_redacted_errors(self):
        class Response(io.BytesIO):
            def read(self,n=-1):self.requested=n;return super().read(n)
        response=Response(b'{"id":123}')
        with patch("mission_control.insights_transport.build_opener") as build:
            build.return_value.open.return_value=response
            self.assertEqual(transport.request("https://us.posthog.com/api/projects/123/","synthetic")["id"],123)
            req=build.return_value.open.call_args[0][0]
            self.assertEqual(req.get_method(),"GET");self.assertEqual(req.headers["Authorization"],"Bearer synthetic")
            self.assertEqual(response.requested,2097153)
        for code in (401,403,429,500):
            error=HTTPError("https://provider.test",code,"secret-provider-detail",{},None)
            with patch("mission_control.insights_transport.build_opener") as build:
                build.return_value.open.side_effect=error
                with self.assertRaises(transport.ProviderFailure) as caught:transport.request("https://provider.test","synthetic")
                self.assertNotIn("secret-provider-detail",str(caught.exception))
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b"x"*2097153):
            with patch("mission_control.insights_transport.build_opener") as build:
                build.return_value.open.return_value=Response(raw)
                with self.assertRaises(transport.ProviderFailure):transport.request("https://provider.test","synthetic")

    def test_actual_loopback_routes_csrf_bounds_workspace_and_disconnect(self):
        from tests import test_http as http_module
        fixture=http_module.HTTPTests(methodName="runTest");fixture.setUp()
        try:
            route="/api/apps/sample-one/insights/setup"
            self.assertEqual(fixture.request(route,setup_body(),headers={"X-CSRF-Token":"wrong"})[0],403)
            self.assertEqual(fixture.request(route,raw=b"x"*8193)[0],400)
            with patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])):
                code,result,_=fixture.request(route,setup_body())
            self.assertEqual(code,201);sid=result["source_id"]
            workspace=fixture.request("/api/apps/sample-one")[1]
            self.assertEqual(workspace["insights"]["sources"][0]["status"],"CONNECTED")
            self.assertEqual(fixture.request("/api/apps/sample-two/insights/"+sid+"/read",{"confirm_read":True})[0],404)
            self.assertEqual(fixture.request("/api/apps/sample-one/insights/"+sid+"/disconnect",{"version":1,"confirm_disconnect":True})[0],200)
        finally:fixture.tearDown()

    def test_retire_failed_cleanup_then_disconnect_retry(self):
        sid=self.create()["source_id"]
        original_delete=FakeVault.delete
        with patch.object(FakeVault,"delete",side_effect=Invalid("native cleanup failed")),patch("mission_control.insights_transport.request",side_effect=copy.deepcopy(payloads()["posthog"])):
            result=self.insights.setup("sample-one",{**setup_body(),"version":1})
        self.assertEqual(result["cleanup"],"PRIOR_LOCAL_KEY_CLEANUP_REQUIRED")
        self.assertEqual(len(FakeVault.values),2)
        with patch.object(FakeVault,"delete",side_effect=Invalid("native cleanup failed")):
            result=self.insights.disconnect("sample-one",sid,{"version":2,"confirm_disconnect":True})
        self.assertEqual(result["status"],"CLEANUP_REQUIRED")
        self.assertEqual(self.insights.tick()["status"],"IDLE")
        self.assertEqual(self.insights.disconnect("sample-one",sid,{"version":3,"confirm_disconnect":True})["status"],"DISCONNECTED")
        self.assertEqual(FakeVault.values,{})

    def test_missing_or_mismatched_native_key_reconnects_and_not_false_connected(self):
        sid=self.create()["source_id"]
        FakeVault.values[next(iter(FakeVault.values))]["binding"]["app_id"]="sample-two"
        result=self.insights.refresh("sample-one",sid,{"confirm_read":True})
        self.assertEqual(result["status"],"PERMISSION_REQUIRED")
        self.assertEqual(len(self.insights.list("sample-one")["reports"]),1)

    def test_invalid_response_keeps_previous_data_and_unknown_report_fields_reject(self):
        sid=self.create()["source_id"]
        with patch("mission_control.insights.read",side_effect=Invalid("private@example.test")):
            result=self.insights.refresh("sample-one",sid,{"confirm_read":True})
        self.assertEqual(result["status"],"READ_FAILED")
        self.assertNotIn("private@example.test",str(result))
        for action in (lambda:self.insights.refresh("sample-one",sid,{"confirm_read":False}),
                       lambda:self.insights.disconnect("sample-one",sid,{"version":1,"confirm_disconnect":False}),
                       lambda:self.insights.disconnect("sample-one",sid,{"version":False,"confirm_disconnect":True})):
            with self.assertRaises(Invalid):action()

    def test_report_history_cap_and_bounded_synthetic_read_performance(self):
        import time
        sid=self.create()["source_id"]
        started=time.monotonic()
        with patch("mission_control.insights_transport.request",side_effect=lambda *args: {"id":123} if args[0].endswith("/123/") else {"results":[]}):
            for _ in range(105):self.insights.refresh("sample-one",sid,{"confirm_read":True})
        self.assertEqual(len(self.insights.list("sample-one")["reports"]),100)
        self.assertLess(time.monotonic()-started,10)

    def test_request_post_json_and_network_timeout_redirection_errors(self):
        class Response(io.BytesIO):pass
        with patch("mission_control.insights_transport.build_opener") as build:
            build.return_value.open.return_value=Response(b'{"results":[]}')
            transport.request("https://us.posthog.com/api/projects/123/query/","synthetic",{"query":{"kind":"HogQLQuery"}})
            req=build.return_value.open.call_args[0][0]
            self.assertEqual(req.get_method(),"POST");self.assertEqual(json.loads(req.data)["query"]["kind"],"HogQLQuery")
            self.assertEqual(build.return_value.open.call_args.kwargs["timeout"],15)
        for error in (URLError("private-network-detail"),TimeoutError(),OSError("private-network-detail")):
            with patch("mission_control.insights_transport.build_opener") as build:
                build.return_value.open.side_effect=error
                with self.assertRaises(transport.ProviderFailure) as caught:transport.request("https://provider.test","synthetic")
                self.assertEqual(caught.exception.code,"NETWORK_ERROR")
                self.assertNotIn("private-network-detail",str(caught.exception))
        from mission_control.providers import NoRedirect
        with self.assertRaises(Invalid):NoRedirect().redirect_request(None,None,302,"",{},"https://evil.test")

    def test_aggregate_bounds_and_async_status_never_claim_incomplete_results(self):
        for rows in (True,[["signup_completed",True]],[["signup_completed",float("inf")]],[[1,2]],[["signup_completed",1]]*101):
            with self.assertRaises(Invalid):contract.shape_posthog({"results":rows})
        with self.assertRaises(Invalid):contract.shape_clarity([{}]*1001)
        with self.assertRaises(Invalid):contract.clarity_rows({"information":[{}]*1001})
        with self.assertRaises(Invalid):contract.shape_revenuecat({"object":"overview_metrics","metrics":[{"value":float("nan")}]})
        self.assertEqual(contract.clarity_rows({"metricName":"Traffic","information":[{"url":"private"}]}),[])
        with self.assertRaises(Invalid):contract.config(setup_body()|{"api_key":" "})

    def test_expired_lease_late_completion_cannot_overwrite_new_read(self):
        sid=self.create()["source_id"];old=self.insights.reserve("sample-one",sid,False)
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET lease=0 WHERE id=?",(sid,))
        newer=self.insights.reserve("sample-one",sid,False)
        self.assertEqual(self.insights.complete("sample-one",old,{}, "CONNECTED",None)["status"],"OBSOLETE_RESULT_DISCARDED")
        self.assertNotEqual(old["lease"],newer["lease"])


if __name__=="__main__":unittest.main()
