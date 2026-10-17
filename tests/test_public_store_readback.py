"""Exact public-page assertions and real isolated persistence; no live provider writes."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from mission_control.common import Invalid, digest, canonical
from mission_control.db import connection
from mission_control.store import Store
from mission_control.provider_outbox import Outbox
from mission_control.public_store_readback import PublicStore, body_data
from mission_control.public_store_page import inspect, destination
from tests.test_provider_outbox import APP, OWNER, outbox_fixture, SyntheticApple

COPY="Test the actual app before choosing a plan."
URL="https://apps.apple.com/us/app/synthetic/id12345"
EXPECTED={"country":"us","store_app_id":"12345","locale":"en-US","release":"1","copy":COPY}


def page(copy=COPY,lang="en-US",version="1",url=URL,extra=""):
    return f'<!doctype html><html lang="{lang}"><head><link rel="canonical" href="{url}"><meta property="og:url" content="{url}"></head><body><section data-test-id="shelf-wrapper" class="shelf centered"><p>{copy}</p></section><section id="mostRecentVersion"><div class="metadata"><span>Version {version}</span><time>Today</time></div></section>{extra}</body></html>'


def resource(html=None,**overrides):
    body=(html if html is not None else page()).encode()
    return {"url":URL,"status":200,"headers":{"content-type":["text/html; charset=utf-8"],"set-cookie":["secret"]},"body":body,"bytes":len(body),"sha256":hashlib.sha256(body).hexdigest(),**overrides}


class Reader:
    def __init__(self,html=None):self.html=html;self.calls=[]
    def read(self,url,cap,permit):
        self.calls.append((url,cap));assert permit(url) and permit(URL)
        assert not permit("https://localhost/us/app/id12345")
        return resource(self.html)


class PageTests(unittest.TestCase):
    def test_exact_identity_language_version_copy(self):
        report=inspect(resource(),EXPECTED)
        self.assertEqual(report["status"],"SERVER_RENDERED_COPY_OBSERVED")
        self.assertTrue(all(report["checks"].values()))
        self.assertNotIn("secret",json.dumps(report));self.assertNotIn(COPY,json.dumps(report))

    def test_host_country_id_and_query_boundaries(self):
        for url in ("https://evil.invalid/us/app/id12345","https://apps.apple.com/ca/app/id12345","https://apps.apple.com/us/app/id123456","https://apps.apple.com/us/app/id12345?q=1","https://apps.apple.com/us/app/id12345#x","https://user@apps.apple.com/us/app/id12345","http://apps.apple.com/us/app/id12345"):
            with self.subTest(url=url):self.assertFalse(destination(url,"us","12345"))
        for url in (URL,"https://apps.apple.com/us/app/id12345"):self.assertTrue(destination(url,"us","12345"))

    def test_every_identity_assertion_must_match(self):
        for html,final in ((page(url=URL.replace("us/","ca/")),URL),(page(),URL.replace("12345","99999")),(page().replace('property="og:url" content="'+URL,'property="og:url" content="'+URL.replace("12345","99999")),URL)):
            self.assertIn("IDENTITY_MISMATCH",inspect(resource(html,url=final),EXPECTED)["reasons"])

    def test_language_version_and_word_boundaries(self):
        for html,reason in ((page(lang="en-GB"),"LANGUAGE_MISMATCH"),(page(version="10"),"VERSION_MISMATCH"),(page(copy="X"+COPY),"COPY_NOT_OBSERVED"),(page(copy=COPY.lower()),"COPY_NOT_OBSERVED")):
            self.assertIn(reason,inspect(resource(html),EXPECTED)["reasons"])
        self.assertEqual(inspect(resource(page(copy="Test the actual app<br>before choosing a plan.")),EXPECTED)["status"],"SERVER_RENDERED_COPY_OBSERVED")

    def test_hidden_script_dialog_and_review_cannot_supply_copy(self):
        for hidden in (f'<script>{COPY}</script>',f'<style>{COPY}</style>',f'<template>{COPY}</template>',f'<dialog>{COPY}</dialog>',f'<span hidden>{COPY}</span>',f'<span aria-hidden="true">{COPY}</span>',f'<span style="display: none">{COPY}</span>',f'<span style="visibility:hidden">{COPY}</span>'):
            self.assertIn("COPY_NOT_OBSERVED",inspect(resource(page(copy=hidden)),EXPECTED)["reasons"])
        self.assertIn("COPY_NOT_OBSERVED",inspect(resource(page(copy="Other copy",extra=f'<article class="review">{COPY}</article>')),EXPECTED)["reasons"])

    def test_ambiguous_and_unknown_markup_fail_closed(self):
        for html in (page().replace('class="shelf centered"','class="different"'),page(extra='<section data-test-id="shelf-wrapper" class="shelf centered">'+COPY+'</section>'),page().replace('</head>','<link rel="canonical" href="'+URL+'"></head>'),page().replace('</body>','</wrong></body>'),page().replace('lang="en-US"','lang="en-US" lang="en-US"')):
            self.assertIn("MARKUP_UNSUPPORTED",inspect(resource(html),EXPECTED)["reasons"])
        footer=f'<section id="privacyFooter" data-test-id="shelf-wrapper" class="shelf centered">{COPY}</section>'
        self.assertIn("COPY_NOT_OBSERVED",inspect(resource(page(copy="Other",extra=footer)),EXPECTED)["reasons"])

    def test_http_mime_empty_copy_and_bounded_language(self):
        self.assertEqual(inspect(resource(status=429),EXPECTED)["reasons"],["HTTP_UNAVAILABLE"])
        self.assertEqual(inspect(resource(headers={"content-type":["application/json"]}),EXPECTED)["reasons"],["CONTENT_TYPE_UNSUPPORTED"])
        self.assertIn("COPY_NOT_OBSERVED",inspect(resource(),{**EXPECTED,"copy":""})["reasons"])
        self.assertIsNone(inspect(resource(page(lang="x"*500)),EXPECTED)["language"])
        self.assertEqual(inspect(resource(page().replace('<p>','<p aria-hidden style>')),EXPECTED)["status"],"SERVER_RENDERED_COPY_OBSERVED")

    def test_capped_parse_performance(self):
        sample=resource(page(copy=COPY+"x"*950000));started=time.monotonic()
        for _ in range(20):self.assertTrue(inspect(sample,EXPECTED)["checks"]["markup"])
        self.assertLess(time.monotonic()-started,5)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"state.sqlite",seed=False)
        self.remote=SyntheticApple();self.data=outbox_fixture(self.store)
        with patch("mission_control.store_actions.request",side_effect=self.remote):self.action=Outbox(self.store).prepare(APP,OWNER,self.data)
        self.checks=PublicStore(self.store);self.body={"manifest_version":self.store.app(APP)["version"],"action_hash":self.action["hash"],"country":"us"}

    def tearDown(self):self.tmp.cleanup()

    def run_check(self,reader=None):return self.checks.run(APP,self.action["id"],self.body,reader or Reader())

    def test_read_records_history_without_action_mutation_and_survives_restart(self):
        before=Outbox(self.store).get(APP,self.action["id"])
        reader=Reader();event=self.run_check(reader)
        self.assertEqual(reader.calls,[("https://apps.apple.com/us/app/id12345",1048576)])
        self.assertEqual(event["detail"]["report"]["status"],"SERVER_RENDERED_COPY_OBSERVED")
        after=Outbox(self.store).get(APP,self.action["id"])
        self.assertEqual({k:v for k,v in before.items() if k!="events"},{k:v for k,v in after.items() if k!="events"})
        self.assertEqual(self.remote.writes,0)
        restored=PublicStore(Store(self.store.path,seed=False));first=restored.list(APP)
        self.assertEqual(first,restored.list(APP));self.assertEqual(first[self.action["id"]][0],event)
        self.assertEqual(event["detail"]["provider_write"],"NOT_RUN")
        self.assertEqual(event["detail"]["growth"],"NOT_MEASURED")

    def test_closed_request_schema_and_stale_action_hash(self):
        for body in ({},{**self.body,"url":URL},{**self.body,"country":"US"},{**self.body,"manifest_version":True},{**self.body,"action_hash":"bad"},{**self.body,"country":"a"}):
            with self.assertRaises(Invalid):body_data(body)
        reader=Reader()
        with self.assertRaises(Invalid):self.checks.run(APP,self.action["id"],{**self.body,"action_hash":"a"*64},reader)
        self.assertFalse(reader.calls)

    def test_foreign_namespace_and_stale_manifest_rejected_before_read(self):
        self.store.save_app("other",{"name":"Other"});reader=Reader()
        with self.assertRaises((Invalid,KeyError)):self.checks.run("other",self.action["id"],self.body,reader)
        self.store.save_app(APP,{**self.store.app(APP)["data"],"release":"2"},self.body["manifest_version"])
        with self.assertRaises(Invalid):self.run_check(reader)
        self.assertFalse(reader.calls)

    def test_source_changed_during_network_does_not_commit(self):
        def change(*args,**kwargs):
            record=next(r for r in self.store.records(APP) if r["id"]==self.data["record_id"])
            self.store.save_record(APP,{**record,"data":{**record["data"],"promotional_text":"Changed"}})
            return resource()
        with self.assertRaises(Invalid):self.run_check(Mock(read=change))
        self.assertFalse(self.checks.list(APP)[self.action["id"]])

    def test_network_exception_redaction_retry_and_immutable_history(self):
        failed=self.run_check(Mock(read=Mock(side_effect=OSError("api_key=private-secret"))))
        self.assertEqual(failed["detail"]["report"]["status"],"READ_UNAVAILABLE")
        self.assertNotIn("private-secret",json.dumps(failed))
        good=self.run_check();history=self.checks.list(APP)[self.action["id"]]
        self.assertEqual(len(history),2);self.assertEqual(history[0],failed);self.assertEqual(history[1],good)

    def test_time_bound_and_source_currentness(self):
        event=self.run_check()
        with patch("mission_control.public_store_readback.now",return_value="2099-01-01T00:00:00+00:00"):
            self.assertEqual(self.checks.list(APP)[self.action["id"]][0]["evidence_status"],"STALE_TIME")
        with patch("mission_control.public_store_readback.now",return_value="2000-01-01T00:00:00+00:00"):
            self.assertEqual(self.checks.list(APP)[self.action["id"]][0]["evidence_status"],"STALE_TIME")
        self.store.save_app(APP,{**self.store.app(APP)["data"],"name":"Changed"},self.body["manifest_version"])
        self.assertEqual(self.checks.list(APP)[self.action["id"]][0]["evidence_status"],"STALE_SOURCE")

    def test_packet_and_event_integrity(self):
        event=self.run_check()
        with connection(self.store.path) as db:db.execute("UPDATE provider_action_events SET hash=? WHERE id=?",("a"*64,event["id"]))
        with self.assertRaises(Invalid):self.checks.list(APP)

    def test_history_cap_and_expired_approval_cannot_grant_send(self):
        with patch("mission_control.public_store_readback.now",return_value="2099-01-01T00:00:00+00:00"):
            event=self.run_check()
        self.assertEqual(event["detail"]["report"]["status"],"SERVER_RENDERED_COPY_OBSERVED")
        with connection(self.store.path) as db:
            for _ in range(99):db.execute("INSERT INTO provider_action_events(action_id,data,hash,created) VALUES(?,?,?,?)",(self.action["id"],canonical({k:v for k,v in event.items() if k not in ("id","hash","evidence_status")}),event["hash"],event["observed_at"]))
        with self.assertRaises(Invalid):self.run_check()
        self.assertEqual(Outbox(self.store).get(APP,self.action["id"])["status"],"WAITING_APPROVAL")


if __name__=="__main__":unittest.main()
