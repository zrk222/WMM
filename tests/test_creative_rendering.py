"""Real native decoding, durable recovery and transactional render portability."""
import base64
import copy
import hashlib
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import zlib
from mission_control.common import Invalid,digest
from mission_control.store import Store
from mission_control.service import Service
from mission_control.db import connection
from mission_control.creative_briefs import Briefs
from mission_control.creative_rendering import Renders,render_request,current_request,owned,folder_for,render_rows,heartbeat,artifact_file
from mission_control.media_native import capability,caption_lines,supported,filters,render_native,validate_video,video_metadata,invoke
from mission_control.media_portable import export_media,media_envelope,media_row,source_request,portable_bytes,restore_media,validate_bytes,media_payload
from mission_control.worker import run_once,claim,jobs
from tests.test_creative_production import ready_production

APP="render-test"


def synthetic_png():
    """Build a valid color-grid PNG fixture; this is never real product media."""
    def chunk(kind,raw):return struct.pack(">I",len(raw))+kind+raw+struct.pack(">I",zlib.crc32(kind+raw)&0xffffffff)
    width,height=240,360
    rows=b"".join(b"\0"+bytes((30+y%90,110,120)) * width for y in range(height))
    return b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(rows))+chunk(b"IEND",b"")


def prepared_render(store,app_id=APP):
    """Bind an explicitly synthetic valid image to isolated passing fixture proof."""
    _,_,_,definition=ready_production(store,app_id)
    service=Service(store);upload=service.upload(app_id,"synthetic-grid.png",synthetic_png())
    asset=service.evidence(app_id,dict(kind="asset",title="Synthetic fixture grid",source="Synthetic native rendering fixture; not a production screenshot",data=dict(upload["data"],authentic=True,rights_cleared=True,device="Synthetic QA grid")))
    definition["asset_ids"]=[asset["id"]]
    brief=Briefs(store).save(app_id,{"data":definition})
    return brief,dict(brief_id=brief["id"],brief_hash=brief["hash"],shape="PORTRAIT")


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"source/state.sqlite")
        self.brief,self.request=prepared_render(self.store);self.renders=Renders(self.store)

    def tearDown(self):self.tmp.cleanup()

    def queue(self,key="native-test"):return self.renders.queue(APP,dict(data=self.request,request_key=key))

    def test_actual_native_video_decode_download_scope_and_portable_replay(self):
        self.assertEqual(capability()["status"],"READY","Native tools must be installed for this integration profile")
        queued=self.queue();self.assertEqual(self.queue()["id"],queued["id"])
        self.assertTrue(run_once(self.store));job=jobs(self.store,APP)[0]
        self.assertEqual(job["status"],"SUCCEEDED",job["result"])
        self.assertEqual(job["attempts"],1)
        rows=self.renders.list(APP)["items"];self.assertEqual(len(rows),1);row=rows[0]
        path,data=artifact_file(self.store,APP,row["id"])
        self.assertEqual(validate_video(path,data["request"]),data["artifact"])
        self.assertEqual(video_metadata(path)["height"],1280)
        self.assertEqual(data["request"]["captions"],[b["script"] for b in self.brief["data"]["content"]["beats"]])
        self.assertEqual((row["status"],data["publication"],data["visual_review"]),("CURRENT","NOT_RUN","REQUIRED"))
        self.assertEqual(self.renders.list("sample-two")["items"],[])
        with self.assertRaises(Invalid):artifact_file(self.store,"sample-two",row["id"])
        with self.assertRaises(Invalid):artifact_file(self.store,APP,"../unsafe")
        snapshot=self.store.export(APP);target=Store(Path(self.tmp.name)/"restore/state.sqlite")
        target.restore(snapshot);restored=artifact_file(target,APP,row["id"])[0]
        self.assertEqual(path.read_bytes(),restored.read_bytes())
        self.assertEqual(Renders(target).list(APP)["items"],rows)
        for mutation in ("scope","source","caption","bytes","metadata","missing","unreferenced"):
            bad=copy.deepcopy(snapshot);media=bad["payload"]["media"];entry=media["rows"][0]
            if mutation=="scope":entry["app_id"]="sample-two"
            if mutation=="source":entry["data"]["request"]["brief_hash"]="wrong"
            if mutation=="caption":entry["data"]["request"]["captions"][0]="Invented claim"
            if mutation=="bytes":media["files"][0]["base64"]=base64.b64encode(b"fake-video").decode()
            if mutation=="metadata":entry["data"]["artifact"]["metadata"]["height"]=720
            if mutation=="missing":media["files"]=[]
            if mutation=="unreferenced":media["files"].append(dict(id="unexpected",base64=base64.b64encode(b"x").decode()))
            entry["hash"]=digest(entry["data"]);bad["sha256"]=digest(bad["payload"])
            rejected=Store(Path(self.tmp.name)/("rejected-"+mutation)/"state.sqlite")
            with self.subTest(mutation=mutation),self.assertRaises(Invalid):rejected.restore(bad)
            self.assertNotIn(APP,[a["id"] for a in rejected.apps()])
            self.assertFalse(list((rejected.path.parent/"renders").rglob("*.mp4")))
        raw=path.read_bytes();path.write_bytes(b"modified")
        with self.assertRaisesRegex(Invalid,"changed"):artifact_file(self.store,APP,row["id"])
        self.assertEqual(self.renders.list(APP)["items"][0]["status"],"STALE_OR_UNAVAILABLE")
        path.write_bytes(raw)

    def test_contract_missing_tools_source_shape_and_caption_readability(self):
        self.assertTrue(supported("A"));self.assertFalse(supported("\x00"))
        self.assertIn("expansion=none",filters("LANDSCAPE"))
        self.assertTrue(folder_for(self.store,APP).name==APP)
        with connection(self.store.path) as db:
            frozen=render_request(db,self.store,APP,self.request);current_request(db,self.store,APP,frozen)
            self.assertEqual(render_rows(db,APP),[]);self.assertEqual(restore_media(db,APP,None),{})
            with self.assertRaises(Invalid):current_request(db,self.store,APP,dict(frozen,captions=["forged"]))
        self.assertEqual(export_media(self.store,APP),dict(rows=[],files=[]))
        self.assertEqual(portable_bytes([]),{})
        for value in ({},None,dict(rows="bad",files=[])):
            with self.assertRaises(Invalid):media_payload(value)
        with self.assertRaises(Invalid):media_envelope(APP,{})
        for changes in ({"shape":"SQUARE"},{"brief_hash":"wrong"},{"brief_id":"foreign"}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.renders.queue(APP,dict(data=dict(self.request,**changes),request_key="bad"))
        with patch("mission_control.creative_rendering.capability",return_value=dict(status="UNAVAILABLE",repair="Install native tools")):
            with self.assertRaisesRegex(Invalid,"Install native"):self.queue()
        for script in ("", "word "*100,"日本語", "control\x01"):
            with self.subTest(script=script),self.assertRaises(Invalid):caption_lines(script,7.5,"PORTRAIT")
        self.assertEqual(caption_lines("Literal %{metadata:secret} and https://example.com",30,"PORTRAIT").replace("\n"," "),"Literal %{metadata:secret} and https://example.com")
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],release="changed"),app["version"])
        with self.assertRaisesRegex(Invalid,"proof"):self.queue()
        self.assertEqual(jobs(self.store,APP),[])
        with self.assertRaisesRegex(Invalid,"guided"):Service(self.store).queue(APP,dict(action="render",data={},request_key="bad"))

    def test_cancel_stop_and_superseded_lease_never_commit(self):
        queued=self.queue();job=claim(self.store)
        self.assertEqual(job["attempts"],1);heartbeat(self.store,job)
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET attempts=attempts+1 WHERE id=?",(job["id"],))
        with self.assertRaisesRegex(Invalid,"superseded"):heartbeat(self.store,job)
        Service(self.store).cancel(APP,queued["id"])
        stopped=threading.Event();stopped.set()
        with self.assertRaisesRegex(Invalid,"stopped"):heartbeat(self.store,job,stopped)
        self.queue("cancel-running")
        def cancel(folder,request,screens,alive):
            active=next(j for j in jobs(self.store,APP) if j["status"]=="RUNNING")
            Service(self.store).cancel(APP,active["id"]);alive()
        with patch("mission_control.creative_rendering.render_native",side_effect=cancel):self.assertTrue(run_once(self.store))
        self.assertTrue(all(j["status"]=="CANCELLED" for j in jobs(self.store,APP)))
        self.assertEqual(self.renders.list(APP)["items"],[])
        self.assertEqual(list((self.store.path.parent/"renders"/APP).iterdir()),[])

    def test_failed_native_and_changed_proof_preserve_source_and_cleanup(self):
        self.queue()
        with patch("mission_control.creative_rendering.render_native",side_effect=Invalid("Native fixture failure")):self.assertTrue(run_once(self.store))
        self.assertEqual(jobs(self.store,APP)[0]["status"],"BLOCKED")
        self.assertEqual(Briefs(self.store).list(APP)[0]["current"],self.brief)
        self.assertEqual(self.renders.list(APP)["items"],[])
        self.queue("stale-after-queue")
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],activation="Changed first value"),app["version"])
        self.assertTrue(run_once(self.store));self.assertEqual(jobs(self.store,APP)[0]["status"],"BLOCKED")
        self.assertEqual(self.renders.list(APP)["items"],[])

    def test_old_snapshot_and_private_child_cancellation(self):
        snapshot=self.store.export(APP);snapshot["payload"].pop("media");snapshot["sha256"]=digest(snapshot["payload"])
        target=Store(Path(self.tmp.name)/"legacy/state.sqlite");target.restore(snapshot)
        self.assertEqual(Renders(target).list(APP)["items"],[])
        import sys,time
        def cancelled():raise Invalid("Cancelled fixture process")
        started=time.monotonic()
        with self.assertRaisesRegex(Invalid,"Cancelled"):invoke([sys.executable,"-c","import time; time.sleep(30)"],Path(self.tmp.name),cancelled,time.monotonic()+10)
        self.assertLess(time.monotonic()-started,5)


if __name__=="__main__":unittest.main()
