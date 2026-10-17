"""Real loopback requests exercise Handler/session/boundary/get/post responses."""
import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
from mission_control.server import Server, Handler
from mission_control.store import Store
from mission_control.common import Invalid
from tests.test_ledger import cohort,event
from tests.test_provider_setup import generated_key
from mission_control.connection_setup import Connections
from tests.test_experiments import prepared,REGISTER,EXPOSE
from unittest.mock import patch
from tests.test_creative_library import reference
from tests.test_creative_production import ready_production,inspection


class HTTPTests(unittest.TestCase):
    def test_resolution_approval_exact_scope_csrf_and_durable_worker(self):
        import uuid
        from mission_control.resolutions import Resolutions
        store=self.server.service.store;app=store.app('sample-one')
        store.save_app('sample-one',{**app['data'],'website':'https://synthetic.example/'},app['version'])
        _,plan=Resolutions(store).proposal('sample-one')
        issue=plan['issues'][0];option=next(o for o in issue['options'] if o['tool']=='inspect_site')
        body=dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],target_url=None,request_key=str(uuid.uuid4()))
        path='/api/apps/sample-one/resolutions/approve'
        self.assertEqual(self.request(path,body,headers={'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/apps/sample-two/resolutions/approve',body)[0],400)
        self.assertEqual(self.request(path+'?execute=anything',body)[0],400)
        self.assertEqual(self.request(path,{**body,'command':'anything'})[0],400)
        code,job,_=self.request(path,body);self.assertEqual(code,201)
        self.assertEqual(job['status'],'QUEUED')
        code,replay,_=self.request(path,body);self.assertEqual(replay['id'],job['id'])
        code,workspace,_=self.request('/api/apps/sample-one');self.assertEqual(code,200)
        self.assertEqual(workspace['resolutions']['history'][0]['status'],'QUEUED')
        self.assertFalse(workspace['resolutions']['automatic_external_writes'])

    def test_campaign_collection_exact_scope_csrf_and_replay(self):
        from mission_control.campaign_inputs import CampaignInputs
        store=self.server.service.store
        app=store.app('sample-one')
        store.save_app('sample-one',{**app['data'],'store_app_id':'123'},app['version'])
        store.save_record('sample-one',dict(kind='connection',title='Synthetic source',source='Test only',
            data=dict(provider='app_store',store_app_id='123',account_id='0',env_ref='SYNTHETIC_TEST_TOKEN')))
        plan=CampaignInputs(store).preview('sample-one')
        body={key:plan[key] for key in ('manifest_version','source_hash')}
        path='/api/apps/sample-one/campaign-inputs'
        self.assertEqual(self.request(path,body,headers={'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('/api/apps/sample-two/campaign-inputs',body)[0],400)
        self.assertEqual(self.request(path+'?override=true',body)[0],400)
        code,result,_=self.request(path,body)
        self.assertEqual(code,201)
        self.assertEqual(len(result['tasks']),3)
        code,replayed,_=self.request(path,body)
        self.assertEqual(code,201)
        self.assertEqual([t['job']['id'] for t in result['tasks']],[t['job']['id'] for t in replayed['tasks']])
        self.assertFalse(result['external_writes'])

    def test_signed_payment_webhook_and_fresh_identity_reconciliation_boundaries(self):
        from tests.test_signed_payments import APP,CONFIG,PaymentFixture,snapshot,signed
        from tests.test_verified_review import OWNER_TOKEN,synthetic_identity
        f=PaymentFixture(self.server.service.store)
        def delivery(raw,header,extra=None):
            url=f"http://127.0.0.1:{self.server.server_port}/api/payments/{APP}/{f.source['id']}"
            request=Request(url,data=raw,headers={"Content-Type":"application/json","Stripe-Signature":header,**(extra or {})},method="POST")
            try:
                with build_opener().open(request,timeout=10) as response:return response.status,json.load(response)
            except HTTPError as error:return error.code,json.load(error)
        with f.context(),patch("mission_control.operator_identity.github_read",side_effect=synthetic_identity):
            self.assertEqual(self.request("/signed-payments.js")[0],200)
            base=f"/api/apps/{APP}/payments"
            self.assertEqual(self.request(base+"/sources",CONFIG)[0],403)
            self.request("/api/identity/login",{"token":OWNER_TOKEN})
            self.assertEqual(self.request(base+"/sources",CONFIG,headers={"X-CSRF-Token":"wrong"})[0],403)
            old=f.source
            self.assertEqual(self.request(base+"/sources/"+old["id"]+"/disconnect",{"version":1,"confirm_disconnect":True})[0],200)
            code,f.source,_=self.request(base+"/sources",CONFIG);self.assertEqual(code,201)
            raw,header=signed(snapshot());sessions=len(self.server.sessions)
            self.assertEqual(delivery(raw,header)[0],200);self.assertEqual(len(self.server.sessions),sessions)
            self.assertEqual(delivery(raw,header)[1]["duplicate"],True)
            self.assertEqual(delivery(raw+b" ",header)[0],403)
            # These headers are rejected before payload intake. Sending a body
            # that the server intentionally will not read causes a Windows TCP
            # reset race; advertise it without transmitting it, proving early
            # rejection. Signature/body tests above still transmit actual bytes.
            self.assertEqual(delivery(b"",header,{"Host":"evil.test","Content-Length":str(len(raw))})[0],403)
            self.assertEqual(delivery(b"",header,{"Content-Type":"text/plain","Content-Length":str(len(raw))})[0],400)
            w=f.payments.list(APP);receipt=w["receipts"][0]
            action=base+"/receipts/evt_one/reconcile"
            body={"receipt_hash":receipt["hash"],"source_id":f.source["id"],"confirm_read":True}
            self.request("/api/identity/logout",{})
            self.assertEqual(self.request(action,body)[0],403)
            self.request("/api/identity/login",{"token":OWNER_TOKEN})
            with patch("mission_control.signed_payments.read",side_effect=Invalid("private synthetic network detail")):
                code,result,_=self.request(action,body);self.assertEqual(code,200);self.assertEqual(result["status"],"FAILED")
            code,result,_=self.request(action,body);self.assertEqual(code,200);self.assertEqual(result["status"],"RECONCILED")
            code,w,_=self.request("/api/apps/"+APP);self.assertEqual(code,200)
            self.assertEqual(w["payments"]["cash"]["complete_totals"][0]["net_cash_minor"],1912)
            for secret in (CONFIG["api_key"],CONFIG["endpoint_secret"],"private@example.test","private synthetic network detail"):
                self.assertNotIn(secret,json.dumps(w))
            self.assertEqual(self.request(base+"/unknown",{})[0],404)
            self.assertEqual(self.request(base+"/sources/"+f.source["id"]+"/disconnect",{"version":1,"confirm_disconnect":True})[0],200)
            self.assertEqual(delivery(raw,header)[0],400)

    def test_outcome_learning_fresh_identity_exact_approval_use_and_rollback(self):
        from tests.test_outcome_learning import LearningFixture,APP,FINAL,clock
        from tests.test_verified_review import OWNER_TOKEN,CHECKER_TOKEN,synthetic_identity
        f=LearningFixture(self.server.service.store);row,_=f.ready();base=f"/api/apps/{APP}/learning";path=base+"/"+row["id"]
        self.assertEqual(self.request("/outcome-learning.js")[0],200)
        payload={"version":row["version"],"hash":row["hash"],"confirm_local_guidance":True}
        self.assertEqual(self.request(path+"/approve",payload)[0],403)
        with clock(FINAL),patch("mission_control.operator_identity.github_read",side_effect=synthetic_identity) as provider:
            self.request("/api/identity/login",{"token":CHECKER_TOKEN})
            self.assertEqual(self.request(path+"/approve",payload,headers={"X-CSRF-Token":"wrong"})[0],403)
            code,approved,_=self.request(path+"/approve",payload);self.assertEqual(code,200)
            self.request("/api/identity/login",{"token":OWNER_TOKEN})
            code,active,_=self.request(path+"/activate",{"version":approved["version"],"hash":approved["hash"],"confirm_activate":True});self.assertEqual(code,200)
            body={"version":active["version"],"hash":active["hash"],"data":f.brief_data}
            code,used,_=self.request(path+"/briefs",body);self.assertEqual(code,201)
            self.assertEqual(used["receipt"]["mode"],"EXPLICIT_NEW_BRIEF_ONLY")
            code,rolled,_=self.request(path+"/rollback",{"version":active["version"],"hash":active["hash"],"confirm_rollback":True,"reason":"Synthetic HTTP rollback"});self.assertEqual(code,200)
            self.assertEqual(rolled["state"],"ROLLED_BACK")
            self.assertEqual(self.request(path+"/briefs",body)[0],400)
            self.assertEqual(self.request(path+"/unknown",{})[0],404)
            self.assertGreaterEqual(sum(c.args[0]=="/user" for c in provider.call_args_list),7)
            view=self.request(f"/api/apps/{APP}")[1]["learning"]
            self.assertIsNone(view["active_id"]);self.assertEqual(len(view["uses"]),1)
            self.assertNotIn(OWNER_TOKEN,json.dumps(view))

    def test_authenticated_provider_action_exact_change_and_readback(self):
        from tests.test_provider_outbox import outbox_fixture,SyntheticApple,APP
        from tests.test_verified_review import OWNER_TOKEN,CHECKER_TOKEN,synthetic_identity
        data=outbox_fixture(self.server.service.store);remote=SyntheticApple();base=f"/api/apps/{APP}/provider-actions"
        self.assertEqual(self.request("/provider-actions.js")[0],200)
        self.assertEqual(self.request(f"/api/apps/{APP}")[1]["access"]["external_execution"],"EXPLICIT_APP_STORE_PROMOTIONAL_TEXT_ONLY")
        self.assertEqual(self.request(base,data)[0],403)
        with patch("mission_control.operator_identity.github_read",side_effect=synthetic_identity),patch("mission_control.store_actions.request",side_effect=remote):
            self.assertEqual(self.request("/api/identity/login",{"token":OWNER_TOKEN})[0],200)
            self.assertEqual(self.request(base+"/destination",{k:data[k] for k in ("record_id","connection_id")})[1]["localization_id"],"LOC-1")
            code,row,_=self.request(base,data);self.assertEqual(code,201)
            approve={"hash":row["hash"],"confirm_provider_change":True};path=base+"/"+row["id"]
            self.assertEqual(self.request(path+"/approve",approve)[0],400)
            self.request("/api/identity/login",{"token":CHECKER_TOKEN})
            self.assertEqual(self.request(path+"/approve",approve)[0],200)
            self.assertEqual(self.request(path+"/execute",{"hash":row["hash"],"confirm_send":True})[0],400)
            self.request("/api/identity/login",{"token":OWNER_TOKEN})
            send={"hash":row["hash"],"confirm_send":True}
            self.assertEqual(self.request(path+"/execute",send,headers={"X-CSRF-Token":"wrong"})[0],403)
            code,result,_=self.request(path+"/execute",send);self.assertEqual(code,200);self.assertEqual(result["status"],"VERIFIED_APPLIED")
            self.assertEqual(self.request(path+"/execute",send)[0],400);self.assertEqual(remote.writes,1)
            self.assertEqual(self.request(path+"/arbitrary",{})[0],404)
            self.assertEqual(self.request(path.replace(APP,"sample-two")+"/reconcile",{})[0],400)
        workspace=self.request(f"/api/apps/{APP}")[1]
        self.assertEqual(workspace["provider_actions"][0]["status"],"VERIFIED_APPLIED")
        self.assertNotIn(OWNER_TOKEN,json.dumps(workspace))
        self.assertFalse(self.request("/api/bootstrap")[1]["automatic_external_writes"])

    def test_verified_identity_and_review_session_boundaries(self):
        from tests.test_verified_review import fixture,OWNER_TOKEN,CHECKER_TOKEN,OWNER,CHECKER,synthetic_identity
        from unittest.mock import patch
        record=fixture(self.server.service.store)
        app="review-test";base=f"/api/apps/{app}"
        self.assertEqual(self.request("/verified-review.js")[0],200)
        self.assertEqual(self.request(base+"/verified-reviews",{"record_id":record["id"]})[0],403)
        with patch("mission_control.operator_identity.github_read",side_effect=synthetic_identity) as provider:
            code,logged,_=self.request("/api/identity/login",{"token":OWNER_TOKEN});self.assertEqual(code,200)
            self.assertEqual(logged["principal"],OWNER["principal"]);self.assertNotIn(OWNER_TOKEN,json.dumps(logged))
            code,row,_=self.request(base+"/verified-reviews",{"record_id":record["id"]});self.assertEqual(code,201)
            self.assertEqual(self.request(base+f"/verified-reviews/{row['id']}/approve",{"hash":row["hash"]})[0],400)
            self.assertEqual(self.request("/api/identity/logout",{})[0],200)
            self.assertEqual(self.request(base+"/verified-reviews",{"record_id":record["id"]})[0],403)
            self.assertEqual(self.request("/api/identity/login",{"token":CHECKER_TOKEN})[0],200)
            code,approved,_=self.request(base+f"/verified-reviews/{row['id']}/approve",{"hash":row["hash"]});self.assertEqual(code,200)
            self.assertEqual(approved["checker"],CHECKER["principal"])
            self.assertEqual(self.request(base+"/access/members",{"login":"fixture-checker","role":"MAKER","status":"ACTIVE","version":1})[0],403)
            self.assertGreaterEqual(sum(c.args[0]=="/user" for c in provider.call_args_list),6)
        for path in ("/api/bootstrap",base):
            payload=self.request(path)[1];self.assertNotIn(CHECKER_TOKEN,json.dumps(payload))
        self.assertEqual(self.request("/api/identity/login",{"token":OWNER_TOKEN},headers={"X-CSRF-Token":"wrong"})[0],403)
        self.assertEqual(self.request("/api/identity/login",{"token":OWNER_TOKEN,"principal":OWNER["principal"]})[0],400)
        self.assertEqual(self.request("/api/identity/login",{"token":"x"*513})[0],400)
        self.assertEqual(self.request("/api/identity/unknown",{})[0],404)
        with patch("mission_control.operator_identity.github_read",side_effect=Invalid("Synthetic revoked token")):
            self.assertEqual(self.request(base+"/verified-reviews",{"record_id":record["id"]})[0],400)
        self.assertEqual(self.request("/api/bootstrap")[1]["identity"]["status"],"SIGNED_OUT")

    def test_native_video_routes_actual_bytes_scope_and_download(self):
        from tests.test_creative_rendering import prepared_render,APP
        from mission_control.worker import run_once
        _,data=prepared_render(self.server.service.store)
        code,job,_=self.request(f"/api/apps/{APP}/production/renders",dict(data=data,request_key="http-video"))
        self.assertEqual(code,201);self.assertEqual(job["status"],"QUEUED")
        self.assertEqual(self.request("/creative-rendering.js")[0],200)
        self.assertTrue(run_once(self.server.service.store))
        _,workspace,_=self.request(f"/api/apps/{APP}");row=workspace["renders"]["items"][0]
        code,video,headers=self.request(f"/api/apps/{APP}/renders/{row['id']}/preview")
        self.assertEqual(code,200);self.assertEqual(headers["Content-Type"],"video/mp4")
        self.assertIn(b"ftyp",video[:64]);self.assertNotIn("Content-Disposition",headers)
        self.assertEqual(headers["Accept-Ranges"],"bytes")
        for value,expected in (("bytes=10-29",video[10:30]),("bytes=-20",video[-20:]),("bytes=20-",video[20:])):
            code,part,headers=self.request(f"/api/apps/{APP}/renders/{row['id']}/preview",headers={"Range":value})
            self.assertEqual(code,206);self.assertEqual(part,expected);self.assertIn("Content-Range",headers)
        for value in ("bytes=-0","bytes=999999999-","bytes=30-20","bytes=0-1,3-4","nonsense"):
            self.assertEqual(self.request(f"/api/apps/{APP}/renders/{row['id']}/preview",headers={"Range":value})[0],416)
        code,download,headers=self.request(f"/api/apps/{APP}/renders/{row['id']}/download")
        self.assertEqual(code,200);self.assertEqual(video,download)
        self.assertIn("attachment",headers["Content-Disposition"])
        self.assertEqual(self.request(f"/api/apps/sample-two/renders/{row['id']}/preview")[0],400)
        self.assertEqual(self.request(f"/api/apps/{APP}/production/renders",dict(data=dict(data,brief_hash="changed"),request_key="bad"))[0],400)
        self.assertEqual(self.request(f"/api/apps/{APP}/renders/{row['id']}/unknown")[0],404)

    def test_acquisition_fixed_panel_routes_and_current_scope(self):
        from tests.test_acquisition_workflows import ready_acquisition,panel_data,answer,APP
        data,_=ready_acquisition(self.server.service.store)
        code,intent,_=self.request(f"/api/apps/{APP}/acquisition/intents",{"data":data});self.assertEqual(code,201)
        code,panel,_=self.request(f"/api/apps/{APP}/acquisition/panels",{"data":panel_data(intent)});self.assertEqual(code,201)
        self.assertEqual(self.request("/acquisition.js")[0],200)
        body={"data":answer(panel)};self.assertEqual(self.request(f"/api/apps/{APP}/acquisition/observations",body)[0],201)
        code,report,_=self.request(f"/api/apps/{APP}/acquisition/reports",{"panel_id":panel["id"]});self.assertEqual(code,201)
        self.assertEqual(report["data"]["partitions"]["HOLDOUT"]["missing"],2)
        self.assertEqual(self.request(f"/api/apps/{APP}/acquisition/attach",{"report_id":report["id"]})[0],400)
        self.assertEqual(self.request("/api/apps/sample-two/acquisition/reports",{"panel_id":panel["id"]})[0],400)
        self.assertEqual(self.request(f"/api/apps/{APP}/acquisition/unknown",{})[0],404)
        for kind in ("intents","panels","observations"):
            self.assertEqual(self.request(f"/api/apps/{APP}/acquisition/{kind}",{"data":None})[0],400)
        workspace=self.request(f"/api/apps/{APP}")[1];self.assertEqual(len(workspace["acquisition"]["observations"]),1)

    def test_ranking_scope_types_and_saved_rationale(self):
        from tests.test_creative_ranking import ready_ranking,APP
        sources=ready_ranking(self.server.service.store);ids=[s["id"] for s in sources]
        self.assertEqual(self.request("/creative-ranking.js")[0],200)
        code,report,_=self.request(f"/api/apps/{APP}/rankings/run",{"reference_ids":ids})
        self.assertEqual(code,201);self.assertEqual(report["data"]["coverage"]["comparable_attention"],7)
        workspace=self.request(f"/api/apps/{APP}")[1]
        self.assertEqual(workspace["rankings"]["report"][0]["input_status"],"CURRENT")
        for body in ({"reference_ids":[None]},{"reference_ids":ids+["foreign"]},{"reference_ids":[]},{"extra":True}):
            self.assertEqual(self.request(f"/api/apps/{APP}/rankings/run",body)[0],400)
        self.assertEqual(self.request("/api/apps/sample-two/rankings/run",{"reference_ids":ids})[0],400)
        self.assertEqual(self.request(f"/api/apps/{APP}/rankings/missing",{})[0],404)
        self.assertEqual(self.request(f"/api/apps/{APP}/rankings/policy",{"data":None})[0],400)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=Server(("127.0.0.1",0),Store(Path(self.tmp.name)/"state.sqlite"))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"
        self.client=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.bootstrap=self.request("/api/bootstrap")[1]

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,body=None,headers=None,raw=None):
        value=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        h={"Origin":self.base,"X-CSRF-Token":self.bootstrap["csrf"]} if hasattr(self,"bootstrap") else {}
        h.update(headers or {})
        request=Request(self.base+path,data=value,headers=h)
        try:response=self.client.open(request)
        except HTTPError as exc:response=exc
        raw=response.read();content_type=response.headers.get("Content-Type","")
        data=json.loads(raw) if content_type.startswith("application/json") else raw
        return response.status,data,response.headers

    def test_static_security_headers_and_workspace(self):
        """GET exercises do_GET, dispatch, boundary, get/get_app and send headers."""
        code,body,headers=self.request("/")
        self.assertEqual(code,200);self.assertIn(b"Mission Control",body)
        self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])
        self.assertEqual(self.request("/style.css")[0],200)
        self.assertEqual(self.request("/app.js")[0],200)
        self.assertEqual(len(self.request("/api/apps/sample-one")[1]["stages"]),12)
        self.assertEqual(self.request("/missing")[0],404)

    def test_experiment_routes_version_scope_and_early_wait(self):
        plan=prepared(self.server.service.store)
        with patch("mission_control.experiments.now",return_value=REGISTER):code,e,_=self.request("/api/apps/sample-one/experiments",plan)
        self.assertEqual(code,201)
        self.assertEqual(self.request("/api/apps/sample-one")[1]["experiments"][0]["hash"],e["hash"])
        url=f"/api/apps/sample-one/experiments/{e['id']}"
        self.assertEqual(self.request(url+"/evaluate",{})[0],400)
        with patch("mission_control.experiments.now",return_value=EXPOSE):
            code,result,_=self.request(url+"/actions",dict(operation="observe",version=1,source="Synthetic receipt",observed_at=EXPOSE))
            self.assertEqual(code,200)
            self.assertEqual(self.request(url+"/evaluate",{})[1]["status"],"AWAITING_ANALYSIS")
        self.assertEqual(self.request(url.replace("sample-one","sample-two")+"/actions",dict(operation="cancel",version=2,reason="Wrong scope"))[0],400)
        self.assertEqual(self.request(url+"/evaluate",{"unexpected":True})[0],404)
        self.assertEqual(self.request(url+"/actions",dict(operation="cancel",version=1,reason="Stale"))[0],400)
        code,schedule,_=self.request(url+"/schedule",dict(enabled=True,interval_hours=24,version=None))
        self.assertEqual(code,200);self.assertTrue(schedule["enabled"])
        self.assertEqual(self.request(url.replace("sample-one","sample-two")+"/schedule",dict(enabled=True,interval_hours=24,version=None))[0],400)
        self.assertEqual(self.request(url+"/schedule",dict(enabled=True,interval_hours=24,version=None))[0],400)
        self.assertEqual(self.request(url+"/actions",dict(operation="cancel",version=2,reason="Done"))[0],200)
        self.assertFalse(self.request("/api/apps/sample-one")[1]["schedules"][0]["enabled"])

    def test_creative_source_save_preview_commit_and_scope(self):
        data=reference();url="/api/apps/sample-one/references"
        code,saved,_=self.request(url,{"data":data});self.assertEqual(code,201)
        self.assertEqual(self.request("/api/apps/sample-one")[1]["references"][0]["current"]["data"],data)
        self.assertEqual(self.request("/api/apps/sample-two/references",dict(id=saved["id"],version=1,data=data))[0],400)
        code,preview,_=self.request(url+"/preview",{"rows":[reference(post_id="source-2")]});self.assertEqual(code,200)
        self.assertEqual(self.request(url+"/import",{k:preview[k] for k in ("rows","preview_hash")})[0],201)
        self.assertEqual(self.request(url,{"data":reference(permission_confirmed=False)})[0],400)
        self.assertEqual(self.request(url+"/unknown",{})[0],404)

    def test_host_origin_and_csrf_rejected(self):
        self.assertEqual(self.request("/",headers={"Host":"attacker.example"})[0],403)
        self.assertEqual(self.request("/api/apps",{},headers={"Origin":"https://attacker.example"})[0],403)
        self.assertEqual(self.request("/api/apps",{},headers={"X-CSRF-Token":"wrong"})[0],403)

    def test_production_routes_scope_version_and_currentness(self):
        source,analysis,records,data=ready_production(self.server.service.store)
        url="/api/apps/production-test/production"
        code,brief,_=self.request(url+"/briefs",{"data":data});self.assertEqual(code,201)
        self.assertEqual(self.request("/api/apps/production-test")[1]["briefs"][0]["current"]["id"],brief["id"])
        self.assertEqual(self.request(url.replace("production-test","sample-two")+"/briefs",{"data":data})[0],400)
        self.assertEqual(self.request(url+"/analyses",{"data":None})[0],400)
        self.assertEqual(self.request(url+"/analyses",{"data":{"reference_id":[]}})[0],400)
        self.assertEqual(self.request(url+"/briefs",{"data":dict(data,analysis_id=[])})[0],400)
        changes=inspection(source,format_family="Corrected from HTTP")
        self.assertEqual(self.request(url+"/analyses",dict(id=analysis["id"],version=1,data=changes))[0],201)
        self.assertEqual(self.request(url+"/analyses",dict(id=analysis["id"],version=1,data=changes))[0],400)
        self.assertEqual(self.request(url+"/briefs",{"data":data})[0],400)
        self.assertEqual(self.request(url+"/unknown",{})[0],404)

    def test_workspace_job_receipt_cannot_precede_completed_schedule(self):
        from mission_control.worker import enqueue
        from mission_control.db import connection
        job=enqueue(self.server.service.store,"sample-one","pipeline",{"stage":0},"schedule-snapshot-race")
        def completed(_app):
            with connection(self.server.service.store.path) as db:db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?",(job["id"],))
            return [{"last_job":job["id"],"last_job_status":"SUCCEEDED"}]
        with patch("mission_control.service.Schedules.list",side_effect=completed):
            workspace=self.request("/api/apps/sample-one")[1]
        self.assertEqual(workspace["jobs"][0]["status"],workspace["schedules"][0]["last_job_status"])

    def test_app_save_reload_export_and_invalid_body(self):
        """POST exercises do_POST, post and post_app; log_message never logs secrets."""
        body={"id":"http-test","data":{"name":"HTTP Test"}}
        self.assertEqual(self.request("/api/apps",body)[0],201)
        self.assertEqual(self.request("/api/apps/http-test")[1]["app"]["data"]["name"],"HTTP Test")
        snapshot=self.request("/api/apps/http-test/export")
        self.assertIn("attachment",snapshot[2]["Content-Disposition"])
        self.assertEqual(self.request("/api/restore",snapshot[1])[0],400)
        self.assertEqual(self.request("/api/apps",raw=b"{bad")[0],400)
        self.assertEqual(self.request("/api/apps",raw=b"[]")[0],400)

    def test_jobs_scope_and_visible_cancel(self):
        body={"action":"pipeline","data":{"stage":0},"request_key":"http-job"}
        code,job,_=self.request("/api/apps/sample-one/jobs",body)
        self.assertEqual(code,201)
        self.assertEqual(self.request(f"/api/apps/sample-two/jobs/{job['id']}/cancel",{})[0],400)
        self.assertEqual(self.request(f"/api/apps/sample-one/jobs/{job['id']}/cancel",{})[0],200)

    def test_upload_and_cross_workspace_file(self):
        code,record,_=self.request("/api/apps/sample-one/files",raw=b"\x89PNG\r\n\x1a\nsynthetic",headers={"X-Filename":"synthetic.png"})
        self.assertEqual(code,201)
        file_id=record["data"]["file_id"]
        self.assertEqual(self.request("/api/apps/sample-one/files/"+file_id)[0],200)
        self.assertNotEqual(self.request("/api/apps/sample-two/files/"+file_id)[0],200)
        self.assertEqual(self.request("/api/apps/sample-one/files/..%2Fstate.sqlite")[0],400)
        self.assertEqual(self.request("/api/apps/sample-one/files",raw=b"script",headers={"X-Filename":"evil.png"})[0],400)

    def test_protected_setup_http_security_and_safe_readback(self):
        key=generated_key()
        body={"provider":"app_store","store_app_id":"123","issuer_id":"issuer-1","key_id":"KEY1","private_key":key}
        route="/api/apps/sample-one/connections"
        self.assertEqual(self.request(route,body,headers={"X-CSRF-Token":"wrong"})[0],403)
        self.assertEqual(self.request(route,{**body,"unexpected":"field"})[0],400)
        self.assertEqual(self.request(route,raw=b" "*8193)[0],400)
        code,data,_=self.request(route,body)
        self.assertEqual(code,201)
        record=data["record"]
        try:
            self.assertEqual(data["status"],"CONFIGURED_UNTESTED")
            self.assertNotIn("PRIVATE KEY",json.dumps(data))
            self.assertNotIn("PRIVATE KEY",json.dumps(self.request("/api/apps/sample-one")[1]))
            self.assertNotIn("PRIVATE KEY",json.dumps(self.request("/api/apps/sample-one/export")[1]))
            path="/api/apps/sample-one/connections/"+record["id"]+"/disconnect"
            self.assertEqual(self.request(path,{"version":0})[0],400)
            self.assertEqual(self.request(path.replace("sample-one","sample-two"),{"version":1})[0],400)
            self.assertEqual(self.request(path,{"version":record["version"]})[0],200)
            self.assertEqual(self.request("/api/apps/sample-one")[1]["connections"][record["id"]]["status"],"DISCONNECTED")
        finally:
            from mission_control.credential_vault import Vault
            Vault().delete(Connections(self.server.service.store).name("sample-one",record["data"]))

    def test_only_loopback_bind(self):
        with self.assertRaises(Invalid):Server(("0.0.0.0",0),self.server.service.store)

    def test_cohort_import_as_of_and_isolation(self):
        self.assertEqual(self.request("/api/apps/sample-one/cohorts",cohort())[0],201)
        rows=[event("i","INSTALL"),event("p","PURCHASE",amount=2000),event("a","COST_ACQUISITION",amount=300),event("d","COST_DELIVERY",amount=100)]
        body={"cohort_id":"pilot-1","events":rows}
        self.assertEqual(self.request("/api/apps/sample-one/events",body)[1]["inserted"],4)
        self.assertEqual(self.request("/api/apps/sample-one/events",body)[1]["duplicates"],4)
        self.assertEqual(self.request("/api/apps/sample-two/events",body)[0],400)
        self.assertEqual(self.request("/api/apps/sample-two/measurement")[1],[])
        self.assertEqual(self.request("/api/apps/sample-one/measurement")[1][0]["contribution_after_acquisition_minor"],1600)
        refund={"cohort_id":"pilot-1","events":[event("r","REFUND","2026-10-03",500,"p")]}
        self.assertEqual(self.request("/api/apps/sample-one/events",refund)[0],201)
        earlier="/api/apps/sample-one/measurement?as_of=2026-10-02T00%3A00%3A00%2B00%3A00"
        self.assertEqual(self.request(earlier)[1][0]["contribution_after_acquisition_minor"],1600)
        self.assertEqual(self.request("/api/apps/sample-one/measurement")[1][0]["contribution_after_acquisition_minor"],1100)
        self.assertEqual(self.request("/api/apps/sample-one/events",body,headers={"X-CSRF-Token":"wrong"})[0],403)


if __name__=="__main__":unittest.main()
