"""Protected real loopback AEO HTTP, with synthetic public sources only."""
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from mission_control.store import Store
from mission_control.server import Server
from mission_control.common import digest
from tests.test_aeo_workflows import CountingReader,APP,ROOT


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"http.sqlite",seed=False)
        self.store.save_app(APP,dict(name="Synthetic HTTP app",website=ROOT))
        self.server=Server(("127.0.0.1",0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.path="/api/apps/"+APP+"/aeo/run"
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        client=HTTPConnection("127.0.0.1",self.server.server_port,timeout=10)
        client.request("POST" if body is not None else "GET",path,body,headers or {})
        response=client.getresponse();result=response.status,dict(response.headers),response.read();client.close();return result
    def protected(self):
        code,headers,raw=self.request("/api/bootstrap");self.assertEqual(code,200)
        return {"Cookie":headers["Set-Cookie"].split(";")[0],"Origin":f"http://127.0.0.1:{self.server.server_port}",
                "X-CSRF-Token":json.loads(raw)["csrf"],"Content-Type":"application/json"}
    def body(self):
        app=self.store.app(APP)
        return json.dumps(dict(app_version=app["version"],app_hash=digest(app["data"]),url=ROOT+"/page",intent_id=None,intent_hash=None)).encode()

    def test_valid_run_workspace_reload_attachment_and_static(self):
        with patch("mission_control.aeo_workflows.PublicReader",CountingReader):
            code,_,raw=self.request(self.path,self.body(),self.protected());self.assertEqual(code,201,raw)
        saved=json.loads(raw)
        code,_,raw=self.request("/api/apps/"+APP);self.assertEqual(code,200,raw)
        row=json.loads(raw)["aeo"]["checks"][0];self.assertEqual(row["id"],saved["id"]);self.assertEqual(row["evidence_status"],"CURRENT")
        code,h,raw=self.request("/api/apps/"+APP+"/aeo/history");self.assertEqual(code,200)
        self.assertIn("attachment",h["Content-Disposition"]);self.assertEqual(json.loads(raw)[0]["data"],saved["data"])
        code,h,raw=self.request("/aeo.js");self.assertEqual(code,200);self.assertIn(b"aeoSubmit",raw)
        self.assertEqual(h["X-Content-Type-Options"],"nosniff")

    def test_host_csrf_origin_exact_route_missing_app_and_duplicates(self):
        good=self.protected()
        cases=[(self.path,{},403),(self.path,{**good,"Origin":"https://evil.example"},403),
               (self.path,{**good,"Host":"evil.example"},403),(self.path+"?ignored=1",good,400),
               (self.path+"/extra",good,400),(self.path.replace(APP,"missing"),good,404)]
        with patch("mission_control.aeo_workflows.PublicReader",CountingReader):
            for path,headers,expected in cases:
                body=self.body()
                if expected==403:
                    # Rejection must precede reading a body. Advertising its
                    # length without sending it also avoids a Windows reset
                    # race when the server closes an unauthorised connection.
                    headers={**headers,'Content-Length':str(len(body))}
                    body=b''
                self.assertEqual(self.request(path,body,headers)[0],expected)
            duplicate=self.body().replace(b'"app_version": 1',b'"app_version": 2,"app_version":1')
            self.assertEqual(self.request(self.path,duplicate,good)[0],400)
        self.assertEqual(self.request("/api/apps/"+APP+"/aeo/history?ignored=1")[0],400)
        self.assertEqual(self.request("/api/apps/missing/aeo/history")[0],404)

if __name__=="__main__":unittest.main()
