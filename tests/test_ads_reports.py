"""Native report behavior using supplied synthetic Apple observations only."""
import copy,json,os,tempfile,time,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.provider_reports import read_report,report_options,Reader
from mission_control.providers import report_request
from mission_control.store import Store
from mission_control.service import Service
from mission_control.worker import run_once,enqueue,jobs


def options(operation="keyword_report"):
    today=datetime.now(timezone.utc).date()
    return {"operation":operation,"campaign_ids":["42"],"start":(today-timedelta(days=6)).isoformat(),"end":today.isoformat()}


def campaign():
    return {"id":42,"adAccountId":456,"promotedObjectType":"APPSTORE_APP","promotedObjectId":"123"}


def keyword(identity=1):
    return {"id":identity,"campaignId":42,"adAccountId":456,"adGroupId":7,"text":"synthetic planning","matchType":"EXACT"}


def row(identity=1,search=False):
    metadata=keyword(identity)
    if search:
        metadata={"campaignId":42,"adAccountId":456,"adGroupId":7,"searchTermText":"synthetic question "+str(identity),"searchTermSource":"AUTO","keyword":keyword(identity)}
    return {"metadata":metadata,"totalMetrics":{"taps":4,"totalInstalls":None,"localSpend":{"amount":"1.23","currency":"USD"}},"granularMetrics":[]}


def page(rows,offset=0,total=None,size=100):
    return {"result":{"rows":rows},"pagination":{"offset":offset,"pageSize":size,"totalCount":len(rows)+offset if total is None else total}}


class AdsReports(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/"reports.sqlite",seed=False)
        for app in ("sample-one","other"):
            self.store.save_app(app,{"name":"Synthetic "+app,"release":"fixture","locale":"en-US"})
        self.service=Service(self.store)
        self.binding={"provider":"apple_ads","account_id":"456","store_app_id":"123","env_ref":"GROWTH_SAMPLE_ONE_SYNTHETIC"}
        self.env=patch.dict(os.environ,{"GROWTH_SAMPLE_ONE_SYNTHETIC":"synthetic-bearer"});self.env.start();self.addCleanup(self.env.stop)

    def read(self,pages,operation="keyword_report"):
        with patch("mission_control.provider_reports.report_request",side_effect=[{"result":[campaign()]},*pages]) as request:
            result=read_report(self.binding,"sample-one",options(operation))
        return result,request

    def connect(self):
        return self.service.evidence("sample-one",{"kind":"connection","title":"Synthetic Ads","source":"Supplied synthetic fixture","data":self.binding})

    def rotate(self,record):
        return self.service.evidence("sample-one",{**record,"data":dict(record["data"],account_id="999")})

    def queue(self,record,key="test"):
        return self.service.queue("sample-one",{"action":"sync","request_key":key,"data":{"connection_id":record["id"],"options":options()}})

    def test_native_keywords_nulls_hashes_and_query(self):
        result,request=self.read([page([row()])])
        self.assertEqual(result["operation"],"keyword_report")
        self.assertEqual(result["reporting_timezone"],"UTC")
        self.assertEqual(result["coverage"],"COMPLETE")
        self.assertEqual(result["coverage_scope"],"PROVIDER_DECLARED_ROWS_ONLY")
        self.assertIsNone(result["rows"][0]["totalMetrics"]["totalInstalls"])
        self.assertEqual(len(result["page_source_hashes"]),2)
        self.assertEqual(request.call_args.args[0],"https://api.ads.apple.com/v1/reports/apps/keywords/query")
        self.assertEqual(request.call_args.args[1]["X-AP-Context"],"adAccountId=456")
        self.assertEqual(request.call_args.args[2]["timeRange"]["granularity"],"DAILY")
        self.assertEqual(request.call_args.args[2]["filters"][0]["value"],["42"])
        self.assertFalse(result["external_writes"])
        self.assertNotIn("synthetic-bearer",json.dumps(result))

    def test_search_timezone_privacy_and_null_keyword(self):
        source=row(search=True);source["metadata"]["keyword"]=None
        result,request=self.read([page([source])],"search_term_report")
        self.assertEqual(request.call_args.args[0],"https://api.ads.apple.com/v1/reports/apps/searchterms/query")
        self.assertEqual(request.call_args.args[2]["timeRange"]["timeZone"],"ORTZ")
        self.assertEqual(result["reporting_timezone"],"ORTZ")
        self.assertTrue(result["privacy_suppression_possible"])
        self.assertIn("suppressed",result["interpretation"])
        self.assertIsNone(result["rows"][0]["metadata"]["keyword"])

    def test_single_day_omits_granularity_and_no_empty_demand_claim(self):
        one=options("search_term_report");one["start"]=one["end"]
        with patch("mission_control.provider_reports.report_request",side_effect=[{"result":[campaign()]},page([])]) as request:
            result=read_report(self.binding,"sample-one",one)
        self.assertNotIn("granularity",request.call_args.args[2]["timeRange"])
        self.assertEqual(result["rows"],[])
        self.assertTrue(result["privacy_suppression_possible"])
        self.assertEqual(result["coverage_scope"],"PROVIDER_DECLARED_ROWS_ONLY")

    def test_foreign_campaign_preflight_prevents_report_request(self):
        for changes in ({"promotedObjectId":"999"},{"adAccountId":999},{"id":99},{"promotedObjectType":"BUSINESS_BRAND"}):
            with patch("mission_control.provider_reports.report_request",return_value={"result":[dict(campaign(),**changes)]}) as network,self.assertRaises(Invalid):
                read_report(self.binding,"sample-one",options())
            self.assertEqual(network.call_count,1)

    def test_row_and_nested_scope_rejects(self):
        for search in (False,True):
            for key,value in (("campaignId",99),("adAccountId",999),("adGroupId",True)):
                source=row(search=search);source["metadata"][key]=value
                with self.assertRaises(Invalid):self.read([page([source])],"search_term_report" if search else "keyword_report")
        for key,value in (("campaignId",99),("adAccountId",999),("adGroupId",8),("id",True),("matchType","invented"),("text","")):
            source=row(search=True);source["metadata"]["keyword"][key]=value
            with self.assertRaises(Invalid):self.read([page([source])],"search_term_report")

    def test_shapes_and_text_bounds_reject(self):
        sources=[dict(row(),totalMetrics=None),dict(row(),granularMetrics={}),dict(row(),metadata=None)]
        for value in ("",False,"x"*4097):
            source=row();source["metadata"]["text"]=value;sources.append(source)
        for source in sources:
            with self.assertRaises(Invalid):self.read([page([source])])
        for malformed in ({"result":{},"pagination":{}},{"result":{"rows":{}},"pagination":{}}):
            with self.assertRaises(Invalid):self.read([malformed])
        for value in ({},"not-an-object",False):
            source=row(search=True);source["metadata"]["keyword"]=value
            with self.assertRaises(Invalid):self.read([page([source])],"search_term_report")

    def test_malformed_context_and_existing_campaign_choice_fail_closed(self):
        with self.assertRaises(Invalid):report_options("apple_ads",None)
        with self.assertRaises(Invalid):report_options("apple_ads",dict(options(),start="bad-date"))
        with patch("mission_control.provider_reports.report_request") as network,self.assertRaises(Invalid):
            read_report(dict(self.binding,account_id="foreign/path"),"sample-one",options())
        network.assert_not_called()
        for response in ({"result":[]},{"result":{}},{"result":[None]}):
            with patch("mission_control.provider_reports.report_request",return_value=response),self.assertRaises(Invalid):
                read_report(self.binding,"sample-one",options())
        malformed=[{"result":None},{"result":{"rows":None}},page([None]),page([{"metadata":campaign(),"totalMetrics":None}])]
        for response in malformed:
            with patch("mission_control.provider_reports.report_request",side_effect=[{"result":[campaign()]},response]),self.assertRaises(Invalid):
                read_report(self.binding,"sample-one",options("campaign_report"))

    def test_pagination_preserves_observations_without_summary_addition(self):
        result,request=self.read([page([row(1)],total=2),page([row(2)],offset=1,total=2)])
        self.assertEqual(len(result["rows"]),2);self.assertEqual(result["pages"],2)
        self.assertEqual(request.call_args.args[2]["pagination"]["offset"],1)
        self.assertEqual(result["coverage"],"COMPLETE")

    def test_duplicates_changes_and_page_size_conflicts_reject(self):
        cases=[
            [page([row()],total=2),page([row()],offset=1,total=2)],
            [page([row()],total=2),page([row(2)],offset=1,total=3)],
            [page([row()],size=0)],
            [page([],total=2)],
            [page([row()],offset=1)],
            [page([row()],total=True)]]
        for pages in cases:
            with self.assertRaises(Invalid):self.read(pages)

    def test_page_cap_bounds_performance_and_partial_coverage(self):
        pages=[page([row(n) for n in range(i,i+100)],offset=i,total=301) for i in (0,100,200)]
        start=time.monotonic();result,request=self.read(pages)
        self.assertLess(time.monotonic()-start,5)
        self.assertEqual(len(result["rows"]),300);self.assertEqual(request.call_count,4)
        self.assertEqual(result["coverage"],"PARTIAL")
        with patch("mission_control.provider_reports.report_request") as network,self.assertRaises(Invalid):
            reader=Reader({});reader.deadline=0;reader.read("https://api.ads.apple.com/v1/campaigns/query",{})
        network.assert_not_called()

    def test_transport_closed_endpoints_and_query_only(self):
        for path in ("keywords","searchterms"):
            url="https://api.ads.apple.com/v1/reports/apps/"+path+"/query"
            with patch("mission_control.providers.build_opener") as opener:
                opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"result":{"rows":[]}}'
                report_request(url,{"Authorization":"Bearer synthetic"},{"filters":[]})
                self.assertEqual(opener.return_value.open.call_args.args[0].method,"POST")
            for bad,body in ((url,None),(url+"?token=x",{}),(url.replace("api.ads.apple.com","evil.example"),{}),(url.replace("/query",""),{})):
                with patch("mission_control.providers.build_opener") as opener,self.assertRaises(Invalid):report_request(bad,{},body)
                opener.assert_not_called()

    def test_options_rejected_before_queue_or_network(self):
        record=self.connect()
        for changes in ({"operation":"create_keyword"},{"campaign_ids":[]},{"campaign_ids":["42","42"]},{"campaign_ids":[True]},{"start":"2020-01-01"},{"end":"2999-01-01"},{"token":"forbidden"}):
            with self.assertRaises(Invalid):self.service.queue("sample-one",{"action":"sync","request_key":"bad","data":{"connection_id":record["id"],"options":dict(options(),**changes)}})
        self.assertEqual(jobs(self.store,"sample-one"),[])
        with self.assertRaises(Invalid):report_options("app_store",options())

    def test_durable_success_failure_and_recovery_preserve_reports(self):
        record=self.connect();job=self.queue(record)
        self.assertEqual(job["data"]["connection_version"],record["version"])
        with patch("mission_control.provider_reports.report_request",side_effect=[{"result":[campaign()]},page([row()])]):run_once(self.store)
        saved=jobs(Store(self.store.path,seed=False),"sample-one")[0]
        self.assertEqual(saved["status"],"SUCCEEDED")
        original=copy.deepcopy(saved)
        self.queue(record,"retry")
        with patch("mission_control.provider_reports.report_request",side_effect=Invalid("Synthetic HTTP 429; retry this read")):run_once(self.store)
        self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"BLOCKED")
        self.assertEqual(next(j for j in jobs(self.store,"sample-one") if j["id"]==original["id"]),original)
        self.queue(record,"recovered")
        with patch("mission_control.provider_reports.report_request",side_effect=[{"result":[campaign()]},page([row()])]):run_once(self.store)
        self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"SUCCEEDED")
        self.assertEqual(jobs(self.store,"other"),[])

    def test_stale_queued_connection_and_foreign_app_reject(self):
        record=self.connect();self.queue(record);changed=self.rotate(record)
        with patch("mission_control.provider_reports.report_request") as network:run_once(self.store)
        network.assert_not_called();self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"BLOCKED")
        with self.assertRaises(Invalid):self.service.queue("sample-one",{"action":"sync","request_key":"stale","data":{"connection_id":record["id"],"connection_version":record["version"],"options":options()}})
        with self.assertRaises(Invalid):self.service.queue("other",{"action":"sync","request_key":"foreign","data":{"connection_id":changed["id"],"options":options()}})

    def test_rotation_during_io_discards_observation_and_legacy_job_blocks(self):
        record=self.connect();self.queue(record)
        def response(url,*args,**kwargs):
            if url.endswith("/campaigns/query"):return {"result":[campaign()]}
            self.rotate(record);return page([row()])
        with patch("mission_control.provider_reports.report_request",side_effect=response):run_once(self.store)
        result=jobs(self.store,"sample-one")[0]
        self.assertEqual(result["status"],"BLOCKED");self.assertNotIn("rows",result["result"])
        enqueue(self.store,"sample-one","sync",{"connection_id":record["id"],"options":options()},"legacy")
        with patch("mission_control.provider_reports.report_request") as network:run_once(self.store)
        network.assert_not_called();self.assertEqual(jobs(self.store,"sample-one")[0]["status"],"BLOCKED")


if __name__=="__main__":unittest.main()
