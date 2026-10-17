"""Custom-event transport, protected update, current coverage and HTTP boundaries."""
import copy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, digest, now
from mission_control.db import connection
from mission_control.store import Store
from mission_control.insights import Insights
from mission_control import event_mapping as core
from mission_control.insights_contract import config, shape_posthog
from mission_control.insights_transport import read, ProviderFailure
from tests.test_measurement_connectors import FakeVault, setup_body, payloads

EVENTS = dict(pageview="page_viewed", signup="web_registration_completed",
              activation="first_result", value="useful_return", purchase="receipt_event", exposure="test_exposed")


def responses(events=EVENTS):
    return [{"id":123},{"results":[[name,index+1] for index,name in enumerate(events.values()) if name]}]


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/"test.sqlite3")
        self.insights=Insights(self.store);FakeVault.values={}
        self.vault=patch("mission_control.insights.Vault",FakeVault);self.vault.start();self.addCleanup(self.vault.stop)

    def create(self, events=EVENTS):
        with patch("mission_control.insights_transport.request",side_effect=responses(events)):
            return self.insights.setup("sample-one",dict(setup_body(),event_map=events))["source_id"]

    def view(self):
        return self.insights.list("sample-one")["sources"][0]["event_coverage"]

    def test_mapping_exact_roles_syntax_distinct_and_at_least_one(self):
        self.assertEqual(core.mapping(EVENTS),EVENTS)
        valid=dict.fromkeys(core.ROLES,"");valid["pageview"]="$page-view.v1"
        self.assertEqual(core.mapping(valid),valid)
        for value in (None,{},dict(EVENTS,extra="x"),dict.fromkeys(core.ROLES,""),
                      dict(EVENTS,value=EVENTS["activation"])):
            with self.subTest(value=value),self.assertRaises(Invalid):core.mapping(value)
        for name in ("x' OR 1=1 --","private@example.test","https://private.test","a b","é",1,False,[], "a"*81):
            with self.subTest(name=name),self.assertRaises(Invalid):core.mapping(dict(EVENTS,value=name))
        self.assertEqual(core.mapping(dict(EVENTS,value="a"*80))["value"],"a"*80)

    def test_config_legacy_and_provider_boundaries(self):
        self.assertNotIn("event_map",config(setup_body()))
        self.assertEqual(config(dict(setup_body(),event_map=EVENTS))["event_map"],EVENTS)
        with self.assertRaises(Invalid):config(dict(setup_body("clarity"),event_map=EVENTS))

    def test_actual_transport_uses_only_mapped_names_and_fixed_host(self):
        with patch("mission_control.insights_transport.request",side_effect=responses()) as request:
            result=read(config(dict(setup_body(),event_map=EVENTS)),"synthetic")
        sql=request.call_args_list[1].args[2]["query"]["query"]
        for name in EVENTS.values():self.assertIn("'"+name+"'",sql)
        self.assertNotIn("'signup_completed'",sql)
        self.assertIn("count()",sql);self.assertNotIn("distinct_id",sql)
        self.assertEqual(result["event_map"],EVENTS)
        self.assertEqual(request.call_args_list[1].args[0],"https://us.posthog.com/api/projects/123/query/")
        with patch("mission_control.insights_transport.request") as request,self.assertRaises(Invalid):
            read(dict(config(setup_body()),event_map=dict(EVENTS,value="x'; SELECT *")),"synthetic")
        request.assert_not_called()

    def test_provider_rejects_unknown_duplicate_unsafe_or_partial_rows(self):
        for rows in ([[["a"],1]],[["unknown",1]],[["page_viewed",1],["page_viewed",2]],
                     [["page_viewed",True]],[["page_viewed",-1]],[["page_viewed",1.5]],
                     [["page_viewed",9007199254740992]]):
            with self.subTest(rows=rows),self.assertRaises(Invalid):shape_posthog({"results":rows},EVENTS)
        self.assertEqual(shape_posthog({"results":[["page_viewed",0]]},EVENTS)[0]["value"],0)
        with self.assertRaises(Invalid):shape_posthog({"results":[],"query_status":{"complete":False}},EVENTS)

    def test_coverage_is_source_bound_and_never_lawful_or_transaction_proof(self):
        self.create()
        view=self.view();self.assertEqual(view["state"],"EVENT_COUNTS_OBSERVED")
        self.assertTrue(view["observation"]["sha256"])
        for field in ("release_verified","consent_verified","transaction_verified"):self.assertFalse(view[field])
        self.assertEqual(self.store.export("sample-one")["payload"]["ledger"],{"cohorts":[],"events":[]})
        self.assertEqual(self.insights.list("sample-two")["sources"],[])

    def test_update_reuses_protected_key_changes_version_and_reads_new_mapping(self):
        sid=self.create();before=copy.deepcopy(FakeVault.values)
        updated=dict(EVENTS,value="return_value_v2")
        with patch("mission_control.insights_transport.request",side_effect=responses(updated)):
            result=self.insights.update_events("sample-one",sid,dict(version=1,event_map=updated,confirm_read=True))
        self.assertEqual(result["read"]["status"],"CONNECTED")
        w=self.insights.list("sample-one")
        self.assertEqual(w["sources"][0]["version"],2)
        self.assertEqual(w["sources"][0]["data"]["event_map"],updated)
        self.assertEqual(len(FakeVault.values),1);self.assertNotEqual(before,FakeVault.values)
        self.assertEqual(next(iter(FakeVault.values.values()))["api_key"],setup_body()["api_key"])
        self.assertEqual(self.view()["state"],"EVENT_COUNTS_OBSERVED")
        self.assertEqual(w["reports"][0]["data"]["source_version"],2)
        self.assertEqual(w["reports"][0]["data"]["configuration_hash"],digest(w["sources"][0]["data"]))

    def test_update_rejects_stale_false_missing_and_cross_app_before_network(self):
        sid=self.create()
        for body in ({},dict(version=True,event_map=EVENTS,confirm_read=True),
                     dict(version=2,event_map=EVENTS,confirm_read=True),
                     dict(version=1,event_map=EVENTS,confirm_read=False),
                     dict(version=1,event_map=EVENTS,confirm_read=True,extra=1)):
            with self.subTest(body=body),patch("mission_control.insights_transport.request") as request,self.assertRaises(Invalid):
                self.insights.update_events("sample-one",sid,body)
            request.assert_not_called()
        with patch("mission_control.insights_transport.request") as request,self.assertRaises(KeyError):
            self.insights.update_events("sample-two",sid,dict(version=1,event_map=EVENTS,confirm_read=True))
        request.assert_not_called()

    def test_disconnected_other_provider_or_bad_binding_cannot_reuse_key(self):
        sid=self.create()
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET status='DISCONNECTED' WHERE id=?",(sid,))
        with self.assertRaises(Invalid):self.insights.update_events("sample-one",sid,dict(version=1,event_map=EVENTS,confirm_read=True))
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET status='CONNECTED' WHERE id=?",(sid,))
        FakeVault.values={}
        with self.assertRaises(Invalid):self.insights.update_events("sample-one",sid,dict(version=1,event_map=EVENTS,confirm_read=True))
        with patch("mission_control.insights_transport.request",side_effect=payloads()["clarity"]):
            other=self.insights.setup("sample-one",setup_body("clarity"))["source_id"]
        with self.assertRaises(Invalid):self.insights.update_events("sample-one",other,dict(version=1,event_map=EVENTS,confirm_read=True))

    def test_missing_zero_and_unmapped_are_three_different_states(self):
        events=dict(EVENTS,value="")
        sid=self.create(events)
        with patch("mission_control.insights_transport.request",side_effect=[{"id":123},{"results":[["page_viewed",0]]}]):
            self.insights.refresh("sample-one",sid,{"confirm_read":True})
        view=self.view();self.assertEqual(view["state"],"COVERAGE_GAPS")
        rows={r["role"]:r for r in view["roles"]}
        self.assertEqual((rows["pageview"]["state"],rows["pageview"]["count"]),("NO_ACTIVITY",0))
        self.assertEqual((rows["signup"]["state"],rows["signup"]["count"]),("NOT_OBSERVED",None))
        self.assertEqual((rows["value"]["state"],rows["value"]["count"]),("NOT_MAPPED",None))

    def test_failed_mapping_keeps_active_coverage_but_active_read_failure_blocks_it(self):
        sid=self.create()
        before=self.insights.list("sample-one")
        keys=copy.deepcopy(FakeVault.values)
        with patch("mission_control.insights_transport.request",side_effect=ProviderFailure("PERMISSION_REQUIRED","Synthetic denied")):
            with self.assertRaisesRegex(Invalid,"Replacement not activated"):
                self.insights.update_events("sample-one",sid,dict(version=1,event_map=dict(EVENTS,value="v2"),confirm_read=True))
        self.assertEqual(self.insights.list("sample-one"),before)
        self.assertEqual(FakeVault.values,keys)
        self.assertEqual(self.view()["state"],"EVENT_COUNTS_OBSERVED")
        self.assertEqual(self.insights.list("sample-one")["sources"][0]["data"]["event_map"],EVENTS)
        with patch("mission_control.insights_transport.request",side_effect=ProviderFailure("PERMISSION_REQUIRED","Synthetic denied")):
            self.insights.refresh("sample-one",sid,{"confirm_read":True})
        self.assertEqual(self.view()["state"],"READ_BLOCKED")
        self.assertIsNone(self.view()["observation"])
        self.insights.disconnect("sample-one",sid,dict(version=1,confirm_disconnect=True))
        self.assertEqual(self.view()["state"],"READ_BLOCKED")
        self.assertEqual(len(self.insights.list("sample-one")["reports"]),1)

    def test_stale_future_and_legacy_observations_require_fresh_read(self):
        self.create();w=self.insights.list("sample-one");source=w["sources"][0];report=w["reports"][0]
        for age in (86401,-10):
            data=dict(report["data"],observed_at=(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat())
            result=core.coverage(source,[dict(report,data=data,hash=digest(data))])
            self.assertEqual(result["state"],"STALE");self.assertIsNone(result["observation"])
        for field in ("source_version","configuration_hash","project_id","provider","event_map"):
            data=dict(report["data"]);data.pop(field)
            self.assertEqual(core.coverage(source,[dict(report,data=data,hash=digest(data))])["state"],"READ_NEEDED")
        data=dict(report["data"],observed_at="invalid")
        self.assertEqual(core.coverage(source,[dict(report,data=data,hash=digest(data))])["state"],"STALE")
        self.assertEqual(core.coverage(source,[dict(report,hash="0"*64)])["state"],"READ_NEEDED")
        self.assertEqual(core.coverage(source,[])["state"],"READ_NEEDED")

    def test_old_inflight_read_cannot_complete_after_mapping_change(self):
        sid=self.create();old=self.insights.reserve("sample-one",sid,False)
        with patch("mission_control.insights_transport.request",side_effect=responses()):
            self.insights.update_events("sample-one",sid,dict(version=1,event_map=EVENTS,confirm_read=True))
        self.assertEqual(self.insights.complete("sample-one",old,{}, "CONNECTED",None)["status"],"OBSOLETE_RESULT_DISCARDED")

    def test_loopback_http_action_csrf_duplicate_json_and_exact_route(self):
        from tests.test_http import HTTPTests
        fixture=HTTPTests(methodName="runTest");fixture.setUp()
        try:
            with patch("mission_control.insights_transport.request",side_effect=responses()):
                code,result,_=fixture.request("/api/apps/sample-one/insights/setup",dict(setup_body(),event_map=EVENTS))
            self.assertEqual(code,201);sid=result["source_id"]
            path="/api/apps/sample-one/insights/"+sid+"/events"
            body=dict(version=1,event_map=EVENTS,confirm_read=True)
            self.assertEqual(fixture.request(path,body,headers={"X-CSRF-Token":"wrong"})[0],403)
            self.assertEqual(fixture.request(path+"?unexpected=1",body)[0],400)
            self.assertEqual(fixture.request(path+"/extra",body)[0],404)
            raw=json.dumps(body).replace('"version": 1','"version": 99, "version": 1').encode()
            self.assertEqual(fixture.request(path,raw=raw)[0],400)
            with patch("mission_control.insights_transport.request",side_effect=responses()):
                self.assertEqual(fixture.request(path,body)[0],200)
            self.assertEqual(fixture.request("/api/apps/sample-two/insights/"+sid+"/events",dict(body,version=2))[0],404)
        finally:fixture.tearDown()

    def test_bounded_projection_performance(self):
        self.create();w=self.insights.list("sample-one");start=time.monotonic()
        for _ in range(1000):core.coverage(w["sources"][0],w["reports"])
        self.assertLess(time.monotonic()-start,2)

    def test_role_rows_matching_report_and_recency_boundaries(self):
        rows=core.role_rows(dict(EVENTS,value=""),{"page_viewed":0,"registered":7})
        self.assertEqual(rows[0]["state"],"NO_ACTIVITY")
        self.assertEqual(rows[3]["state"],"NOT_MAPPED")
        self.assertFalse(core.recent({}));self.assertFalse(core.recent({"observed_at":None}))
        self.assertTrue(core.recent({"observed_at":now()}))
        self.create();w=self.insights.list("sample-one")
        self.assertEqual(core.matching_report(w["sources"][0],w["reports"]),w["reports"][0])
        newer=copy.deepcopy(w["reports"][0]);newer["data"]["source_version"]=99
        newer["hash"]=digest(newer["data"])
        self.assertIsNone(core.matching_report(w["sources"][0],[newer,*w["reports"]]))


if __name__=="__main__":unittest.main()
