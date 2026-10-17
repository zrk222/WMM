"""Source math, honest missingness, current relevance, immutable ranking and replay."""
import copy
import math
from pathlib import Path
import tempfile
import time
import unittest
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.creative_library import Library
from mission_control.creative_attention import age_bucket,comparable_key,freshness,velocity,unavailable,peer_values,robust_attention,attention,log_observation
from mission_control.creative_ranking import (Rankings,bounded_integer,policy_data,policy_weights,relevance_data,current_rows,source_pool,
    ranking_inputs,bind_inputs,review_for,rank_row,partition,select_slate,selection_reason,calculate,TABLES)
from mission_control.creative_rank_portable import (export_rankings,rank_rows,validate_report_row,insert_rank,retained_row,retained_pool,
    retained_source,retained_captures,retained_reviews,report_data,restore_reviews,restore_rankings)
from tests.test_creative_library import reference

APP="ranking-test"
EVALUATED="2026-10-10T00:00:00+00:00"


def policy(**changes):
    return dict(dict(mode="EXPLORATORY",weights=dict(relevance=.6,attention=.2,freshness=.1,cost=.1),max_per_creator=2,max_per_format=3,slate_size=6,
                     holdout_after="2026-10-02T00:00:00+00:00",rationale="Synthetic proposed policy; no calibrated outcome claim"),**changes)


def rank_review(store,source,**changes):
    return dict(dict(reference_id=source["id"],capture_hash=source["current"]["hash"],app_hash=digest(store.app(APP)["data"]),
                     job_fit=2,audience_fit=2,proof_fit=2,rationale="Supplied synthetic fit assessment only",cost_minor=1000),**changes)


def ready_ranking(store,count=9):
    if APP not in [a["id"] for a in store.apps()]:
        store.save_app(APP,dict(name="Synthetic Ranking App",job="Rehearse a difficult conversation",audience="Synthetic users",activation="Saved fictional next step",release="test-build",locale="en-US",currency="USD",website="https://example.com"))
    library=Library(store);ranking=Rankings(store)
    for i in range(count):
        base=reference(post_id="rank-"+str(i),title="Synthetic source "+str(i),creator_id="creator-a" if i<7 else "creator-b",format="product demo" if i<7 else "explanation",traffic_class="ORGANIC",metric_kind="VIEWS",
                       metric_value=50*(i+1),metric_at="2026-10-08T00:00:00+00:00",captured_at="2026-10-08T01:00:00+00:00")
        old=library.save(APP,{"data":base});base.update(metric_value=10000 if i==0 else 100*(i+1),metric_at="2026-10-09T00:00:00+00:00",captured_at=EVALUATED)
        library.save(APP,dict(id=old["id"],version=1,data=base))
    sources=library.list(APP)
    from tests.production_fixtures import ready_capabilities
    ready_capabilities(store,APP,sources,EVALUATED)
    for source in sources:ranking.save(APP,"relevance",{"data":rank_review(store,source)})
    ranking.save(APP,"policy",{"data":policy()})
    return sources


class CreativeRankingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"source/state.sqlite");self.ranking=Rankings(self.store)

    def tearDown(self):self.tmp.cleanup()

    def test_observed_math_denominator_and_velocity(self):
        sources=ready_ranking(self.store);target=next(s for s in sources if s["current"]["data"]["post_id"]=="rank-0")
        result=attention(target,sources,EVALUATED);self.assertEqual(result["n"],6)
        logs=[math.log1p(v) for v in (200,300,400,500,600,700)]
        center=(logs[2]+logs[3])/2;deviations=sorted(abs(x-center) for x in logs);mad=(deviations[2]+deviations[3])/2
        self.assertAlmostEqual(result["log_median"],center);self.assertAlmostEqual(result["log_mad"],mad)
        expected=min(5,(math.log1p(10000)-center)/(1.4826*mad))*6/16/5*2**(-1/30)
        self.assertAlmostEqual(result["score"],expected)
        self.assertEqual({p["id"] for p in result["peers"]},{s["id"] for s in sources if s["current"]["data"]["creator_id"]=="creator-a" and s!=target})
        self.assertEqual(velocity(target),9950);self.assertEqual(attention(target,sources,EVALUATED,"velocity")["n"],6)
        self.assertEqual(age_bucket(target["current"]["data"]),3)

    def test_sparse_unknown_manipulation_and_observation_age(self):
        sources=ready_ranking(self.store);target=copy.deepcopy(sources[0]);d=target["current"]["data"]
        self.assertEqual(attention(target,[target],EVALUATED)["n"],0)
        self.assertIsNone(attention(target,sources[:3],EVALUATED)["score"])
        for changes in ({"creator_id":None},{"traffic_class":"UNKNOWN"},{"published_at":None},{"metric_value":None},{"metric_at":None}):
            altered=copy.deepcopy(target);altered["current"]["data"].update(changes)
            with self.subTest(changes=changes):self.assertIsNone(attention(altered,sources,EVALUATED)["score"])
        peers=[dict(id=str(i),hash="synthetic",value=100,observed_at=EVALUATED) for i in range(5)]
        self.assertIn("zero",robust_attention(1000000,peers,1)["reason"])
        self.assertIsNone(attention(target,sources,"2027-10-10T00:00:00+00:00")["score"])
        for changes in ({"metric_value":0},{"metric_at":"2026-10-08T00:00:00+00:00"},{"traffic_class":"PAID"}):
            altered=copy.deepcopy(target);altered["captures"][-1]["data"].update(changes);self.assertIsNone(velocity(altered))
        other=copy.deepcopy(sources);other[1]["current"]["data"]["locale"]="fr-FR"
        before=attention(target,sources,EVALUATED)["n"];self.assertEqual(attention(target,other,EVALUATED)["n"],before-1)
        self.assertIsNone(freshness(d,"2026-10-01T00:00:00+00:00"))
        huge=copy.deepcopy(target);huge["captures"][-1]["data"]["metric_value"]=10**500
        self.assertIsNone(velocity(huge));self.assertTrue(math.isfinite(log_observation(10**500)))

    def test_policy_and_relevance_types_and_missing_inputs(self):
        for changes in ({"weights":dict(relevance=.4,attention=.4,freshness=.1,cost=.1)},{"weights":dict(relevance=.6,attention=.6,freshness=0,cost=0)},
                        {"slate_size":True},{"max_per_creator":0},{"holdout_after":"2999-01-01T00:00:00+00:00"},{"mode":"SIMPLE_RELEVANCE"},{"mode":[]},{"weights":{"relevance":1}}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):policy_data(policy(**changes))
        self.assertEqual(policy_data(policy(mode="SIMPLE_RELEVANCE",weights=dict(relevance=1,attention=0,freshness=0,cost=0)))["mode"],"SIMPLE_RELEVANCE")
        for changes in ({"job_fit":True},{"proof_fit":4},{"cost_minor":-1},{"app_hash":[]},{"rationale":""}):
            with self.subTest(changes=changes),self.assertRaises(Invalid):relevance_data(dict(reference_id="x",capture_hash="x",app_hash="x",job_fit=1,audience_fit=1,proof_fit=1,rationale="x",cost_minor=0,**{k:v for k,v in changes.items() if k not in {"job_fit","proof_fit","cost_minor","app_hash","rationale"}}) | changes)
        source=Library(self.store).save("sample-one",{"data":reference()})
        with self.assertRaisesRegex(Invalid,"policy"):self.ranking.run("sample-one",{"reference_ids":[source["id"]]})

    def test_ranked_axes_creator_caps_simple_baseline_and_scope(self):
        sources=ready_ranking(self.store);ids=[s["id"] for s in sources];report=self.ranking.run(APP,{"reference_ids":ids})["data"]
        self.assertEqual(report["coverage"],dict(sources=9,eligible=9,comparable_attention=7))
        self.assertEqual(report["evaluation"],"NOT_EVALUATED");self.assertEqual(report["outcomes"],"NOT_RUN")
        by_id={r["reference_id"]:r for r in report["rows"]}
        selected=[by_id[i]["creator_id"] for i in report["slate"]["selected"]]
        self.assertEqual(selected.count("creator-a"),2);self.assertEqual(selected.count("creator-b"),2)
        self.assertTrue(all(r["relevance"]["value"]==2/3 for r in report["rows"]))
        limited=select_slate(report["rows"],dict(report["inputs"]["policy"]["data"],max_per_format=1))
        self.assertEqual(len(limited["selected"]),2);self.assertIn("Format diversity cap",{r["reason"] for r in limited["excluded"]})
        self.assertEqual(self.ranking.list("sample-two")["report"],[])
        with self.assertRaises(Invalid):self.ranking.run("sample-two",{"reference_ids":ids})
        for invalid in ([],[ids[0]]*2,[None],ids+["foreign"]):
            with self.subTest(invalid=invalid),self.assertRaises(Invalid):self.ranking.run(APP,{"reference_ids":invalid})
        changed=copy.deepcopy(report["inputs"])
        for source in changed["sources"]:source["current"]["data"]["creator_id"]=None
        self.assertEqual(len(calculate(changed,EVALUATED)["slate"]["selected"]),1)

    def test_stale_review_version_repair_policy_and_reload(self):
        sources=ready_ranking(self.store);ids=[s["id"] for s in sources];old=self.ranking.run(APP,{"reference_ids":ids})
        source=sources[0];data=dict(source["current"]["data"],title="Changed source")
        Library(self.store).save(APP,dict(id=source["id"],version=2,data=data))
        result=self.ranking.run(APP,{"reference_ids":ids})["data"]
        self.assertEqual(result["coverage"]["eligible"],8)
        self.assertEqual(self.ranking.list(APP)["report"][-1]["input_status"],"STALE_INPUTS")
        review=self.ranking.list(APP)["relevance"][0]
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):self.ranking.validate_review(db,APP,self.store.app(APP),dict(review["current"]["data"],app_hash="wrong"))
        with self.assertRaises(Invalid):self.ranking.save(APP,"relevance",dict(id=review["id"],version=0,data=review["current"]["data"]))
        with self.assertRaises(Invalid):self.ranking.save(APP,"relevance",{"data":review["current"]["data"]})
        source=next(s for s in Library(self.store).list(APP) if s["id"]==source["id"])
        review=next(r for r in self.ranking.list(APP)["relevance"] if r["current"]["data"]["reference_id"]==source["id"])
        self.ranking.save(APP,"relevance",dict(id=review["id"],version=1,data=rank_review(self.store,source)))
        self.assertEqual(self.ranking.run(APP,{"reference_ids":ids})["data"]["coverage"]["eligible"],8)
        from mission_control.production_feasibility import Capabilities
        from tests.production_fixtures import requirement
        capability=Capabilities(self.store)
        needed=next(r for r in capability.list(APP)["requirement"] if r["current"]["data"]["reference_id"]==source["id"])
        capability.save(APP,"requirement",dict(id=needed["id"],version=needed["current"]["version"],data=requirement(source)))
        self.assertEqual(self.ranking.run(APP,{"reference_ids":ids})["data"]["coverage"]["eligible"],9)
        declared=self.ranking.list(APP)["policy"][0]
        new=dict(declared["current"]["data"],rationale="Corrected proposed policy")
        self.ranking.save(APP,"policy",dict(id=declared["id"],version=1,data=new))
        self.assertTrue(all(r["input_status"]=="STALE_INPUTS" for r in self.ranking.list(APP)["report"]))
        self.assertEqual(Rankings(Store(self.store.path)).list(APP),self.ranking.list(APP))
        app=self.store.app(APP);self.store.save_app(APP,dict(app["data"],job="Changed app job"),app["version"])
        with self.assertRaisesRegex(Invalid,"Review"):self.ranking.run(APP,{"reference_ids":ids})

    def test_snapshot_replay_forged_components_and_atomic_recovery(self):
        sources=ready_ranking(self.store);self.ranking.run(APP,{"reference_ids":[s["id"] for s in sources]})
        original=self.store.export(APP);target=Store(Path(self.tmp.name)/"restored/state.sqlite");target.restore(original)
        self.assertEqual(target.export(APP)["payload"]["rankings"],original["payload"]["rankings"])
        for mutation in ("score","peer","scope","identity","version","inputs","reviews"):
            bad=copy.deepcopy(original);item=bad["payload"]["rankings"]["report"][0];row=item["current"]
            if mutation=="score":row["data"]["rows"][0]["score"]=1000
            if mutation=="peer":row["data"]["inputs"]["sources"][0]["captures"][0]["data"]["metric_value"]=999999
            if mutation=="scope":row["app_id"]="sample-two"
            if mutation=="identity":item["id"]=[]
            if mutation=="version":row["version"]=2
            if mutation=="inputs":row["data"]["inputs"]=[]
            if mutation=="reviews":row["data"]["inputs"]["reviews"]=[None]
            row["hash"]=digest(row["data"]);bad["sha256"]=digest(bad["payload"])
            fresh=Store(Path(self.tmp.name)/mutation/"state.sqlite")
            with self.subTest(mutation=mutation),self.assertRaises(Invalid):fresh.restore(bad)
            self.assertNotIn(APP,[a["id"] for a in fresh.apps()])
        legacy=copy.deepcopy(original);del legacy["payload"]["rankings"];legacy["sha256"]=digest(legacy["payload"])
        restored=Store(Path(self.tmp.name)/"legacy/state.sqlite");restored.restore(legacy)
        self.assertEqual(Rankings(restored).list(APP)["report"],[])

    def test_local_history_performance_bound(self):
        sources=ready_ranking(self.store);ids=[s["id"] for s in sources]
        for _ in range(20):self.ranking.run(APP,{"reference_ids":ids})
        start=time.monotonic();reports=self.ranking.list(APP)["report"];elapsed=time.monotonic()-start
        self.assertEqual(len(reports),20);self.assertTrue(all(r["input_status"]=="CURRENT" for r in reports));self.assertLess(elapsed,10)
        print(f"RANKING_HISTORY_20_REPORTS_9_SOURCES_SECONDS={elapsed:.6f}")


if __name__=="__main__":unittest.main()
