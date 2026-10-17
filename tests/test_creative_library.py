"""Permitted source identity, uncertainty, append-only captures and atomic imports."""
import copy
import csv
import io
from pathlib import Path
import tempfile
import unittest
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.creative_library import (Library,reference_data,reference_dates,source_url,source_host,identity,latest_capture,
                                            append_capture,write_reference,import_rows,csv_reference,export_library,restore_capture,restore_library,
                                            date_order,library_snapshot,restore_reference)
from mission_control.store import Store


def reference(**changes):
    return dict(dict(platform="youtube",post_id="public-post-1",title="Synthetic product demo",url="https://example.com/public-post-1",source="Synthetic permitted export; not real engagement",
                     captured_at="2026-10-10T00:00:00+00:00",published_at="2026-10-01T00:00:00+00:00",locale="en-US",traffic_class="UNKNOWN",creator_id=None,
                     format="product demo",metric_kind="UNKNOWN",metric_value=None,metric_at=None,rights="REFERENCE_ONLY",permission_confirmed=True,
                     topic="Rehearsal",relevance_note="Synthetic reference for rehearsal product, not acquisition proof"),**changes)


class CreativeLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"source/state.sqlite");self.library=Library(self.store)

    def tearDown(self):self.tmp.cleanup()

    def test_exact_source_types_and_missing_observations(self):
        data=reference_data(reference());self.assertIsNone(data["metric_value"]);self.assertIsNone(data["creator_id"])
        reference_dates(data);self.assertEqual(identity(data),"youtube:public-post-1")
        date_order(data)
        for changes in ({"permission_confirmed":False},{"permission_confirmed":"true"},{"platform":"made-up"},{"metric_kind":"UNKNOWN","metric_value":10},{"metric_kind":"VIEWS","metric_value":10},{"metric_kind":"VIEWS","metric_value":True,"metric_at":"2026-10-09T00:00:00+00:00"},{"metric_value":-1},{"creator_id":"contact@example.com"},{"published_at":"2999-01-01T00:00:00+00:00"},{"captured_at":"2026-10-01"},{"metric_at":"2026-09-01T00:00:00+00:00"},{"token":"private"}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):reference_data(reference(**changes))

    def test_public_source_url_boundary(self):
        self.assertEqual(source_url("https://example.com/watch?v=public"),"https://example.com/watch?v=public")
        source_host("8.8.8.8");source_host("2606:4700:4700::1111")
        for url in ("http://example.com","https://localhost/x","https://localhost./x","https://127.0.0.1./x","https://127.0.0.1/x","https://127.1/x","https://10.0.0.2/x","https://[::1]/x","https://app.local/x","https://private.internal/x","https://singlehost/x","https://example.com:8443/x","https://example.com:0/x","https://example.com:bad/x","https://@example.com/x","https://user:password@example.com/x","https://example.com/x#private","https://example.com/x?access_token=private","javascript:alert(1)"):
            with self.subTest(url=url),self.assertRaises(Invalid):source_url(url)

    def test_create_duplicate_refresh_scope_and_restart(self):
        data=reference();saved=self.library.save("sample-one",{"data":data})
        duplicate=self.library.save("sample-one",{"data":data});self.assertEqual(duplicate["status"],"UNCHANGED")
        self.assertEqual(duplicate["id"],saved["id"])
        updated=reference(title="Updated synthetic source",metric_kind="VIEWS",metric_value=123,metric_at="2026-10-09T00:00:00+00:00")
        with self.assertRaisesRegex(Invalid,"Refresh"):self.library.save("sample-one",{"data":updated})
        self.library.save("sample-one",dict(id=saved["id"],version=1,data=updated))
        row=self.library.list("sample-one")[0];self.assertEqual(len(row["captures"]),2);self.assertEqual(row["current"]["data"]["metric_value"],123)
        self.assertEqual(row["captures"][0]["data"],data)
        self.assertEqual(Library(Store(self.store.path)).list("sample-one"),self.library.list("sample-one"))
        self.assertEqual(self.library.list("sample-two"),[])
        for body in (dict(id=saved["id"],version=1,data=updated),dict(id=saved["id"],version=2,data=reference(post_id="another")),dict(id=saved["id"],version=2,data=reference(captured_at="2026-10-08T00:00:00+00:00"))):
            with self.assertRaises(Invalid):self.library.save("sample-one",body)
        with self.assertRaises(Invalid):self.library.save("sample-two",dict(id=saved["id"],version=2,data=updated))

    def test_import_preview_conflicts_and_atomic_commit(self):
        data=reference();self.library.save("sample-one",{"data":data})
        second=reference(post_id="public-post-2");preview=self.library.preview("sample-one",{"rows":[second]})
        self.assertEqual(self.library.commit("sample-one",{k:preview[k] for k in ("rows","preview_hash")})["results"][0]["status"],"SAVED")
        conflict=self.library.preview("sample-one",{"rows":[reference(post_id="public-post-3"),reference(title="Conflicting source")]})
        self.assertEqual(conflict["conflicts"],["youtube:public-post-1"])
        with self.assertRaises(Invalid):self.library.commit("sample-one",{k:conflict[k] for k in ("rows","preview_hash")})
        self.assertEqual(len(self.library.list("sample-one")),2)
        bad=copy.deepcopy(preview);bad["rows"][0]["title"]="Changed after preview"
        with self.assertRaisesRegex(Invalid,"preview changed"):self.library.commit("sample-one",{k:bad[k] for k in ("rows","preview_hash")})
        for rows in ([],[data,data],[reference(post_id="p"+str(i)) for i in range(101)]):
            with self.assertRaises(Invalid):import_rows({"rows":rows})

    def test_csv_exact_scalars_and_nullable_preview(self):
        data=reference(metric_kind="VIEWS",metric_value=0,metric_at="2026-10-09T00:00:00+00:00")
        stringrow={k:"" if v is None else str(v).lower() if isinstance(v,bool) else str(v) for k,v in data.items()}
        self.assertEqual(csv_reference(stringrow),data)
        buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=list(data));writer.writeheader();writer.writerow(stringrow)
        preview=self.library.preview("sample-one",{"csv":buffer.getvalue()})
        self.assertEqual(preview["rows"],[data]);self.assertEqual(preview["preview_hash"],digest([data]))
        for changes in ({"metric_value":"-1"},{"metric_value":"1.5"},{"permission_confirmed":"yes"},{"other":"unknown"}):
            with self.assertRaises(Invalid):csv_reference(dict(stringrow,**changes))
        with self.assertRaises(Invalid):import_rows({"csv":"platform,platform\nyoutube,youtube\n"})

    def test_snapshot_source_history_restore_and_tamper_atomic(self):
        saved=self.library.save("sample-one",{"data":reference()})
        self.library.save("sample-one",dict(id=saved["id"],version=1,data=reference(title="Refreshed source")))
        snapshot=self.store.export("sample-one");target=Store(Path(self.tmp.name)/"restored/state.sqlite",seed=False)
        target.restore(snapshot);self.assertEqual(Library(target).list("sample-one"),self.library.list("sample-one"))
        self.assertEqual(export_library(self.store,"sample-one"),snapshot["payload"]["references"])
        for change in ("scope","hash","version","identity","permission","duplicate"):
            bad=copy.deepcopy(snapshot);row=bad["payload"]["references"][0];item=row["captures"][0]
            if change=="scope":row["app_id"]="sample-two"
            if change=="hash":item["hash"]="0"*64
            if change=="version":item["version"]=2
            if change=="identity":row["identity"]="x:other"
            if change=="permission":item["data"]["permission_confirmed"]=False;item["hash"]=digest(item["data"])
            if change=="duplicate":bad["payload"]["references"].append(copy.deepcopy(row))
            bad["sha256"]=digest(bad["payload"]);other=Store(Path(self.tmp.name)/change/"state.sqlite",seed=False)
            with self.subTest(change=change),self.assertRaises(Invalid):other.restore(bad)
            self.assertEqual(other.apps(),[])

    def test_source_helpers_limits_and_capture_owner(self):
        data=reference()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");saved=write_reference(db,"sample-one",data)
            capture=latest_capture(db,"sample-one",saved["id"])
            row={"app_id":"sample-one","id":saved["id"],"identity":identity(data)}
            self.assertEqual(restore_capture(row,capture,1,None),data)
            with self.assertRaises(Invalid):latest_capture(db,"sample-two",saved["id"])
            with self.assertRaises(Invalid):restore_capture(row,dict(capture,reference_id="other"),1,None)
            append_capture(db,"sample-one",saved["id"],reference(title="Next capture"),2)
            restore_library(db,"sample-one",None)
            with self.assertRaises(Invalid):restore_library(db,"sample-one",[{}])
        self.assertEqual(self.library.list("sample-one")[0]["current"]["version"],2)
        for invalid in (None,{},[{}],[{"captures":[]}]*1001,[{"captures":[{}]*5001}]):
            with self.assertRaises(Invalid):library_snapshot(invalid)
        library_snapshot(export_library(self.store,"sample-one"))
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):restore_reference(db,"sample-two",export_library(self.store,"sample-one")[0],set())


if __name__=="__main__":unittest.main()
