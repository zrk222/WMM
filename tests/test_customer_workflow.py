"""Evidence-to-feature linkage, exclusions, source expiry and bounded privacy checks."""
import copy
from datetime import datetime, timezone
import time
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.customer_workflow import (workflow_data, workflow_readout, bounded_rows,
    public_excerpt, observation_data, feature_data, exclusion_data, prototype_observation_time,
    prototype_duration, prototype_feature_ids)

OBSERVED = datetime.fromisoformat("2026-10-22T12:00:00+00:00")


def proposal():
    return dict(release="build-1", locale="en-US", currency="USD", buyer="Synthetic independent app founder",
        micro_behavior="Reconcile the first renewal after a trial", desired_outcome="Understand the missing billing step",
        sources=[dict(id="public-one", url="https://synthetic.example/customer", content_sha256="a" * 64,
            observed_at="2026-10-01T00:00:00+00:00", expires_at="2026-12-01T00:00:00+00:00", availability="AVAILABLE",
            excerpt="Synthetic complaint: I repeatedly reconcile trial charges manually.", evidence_type="FIRSTHAND_COMPLAINT",
            frequency="Synthetic weekly observation", impact="Time cost remains unmeasured")],
        features=[dict(id="renewal-report", description="Show first-renewal evidence", source_ids=["public-one"],
                       validation="Observe whether a tester can identify the missing step")],
        excluded_features=[dict(feature="CRM", reason="The source describes a billing reconciliation workflow")],
        prototype_test="Record task completion and corrections in a consented prototype session; payment remains untested")


def prototype():
    return dict(observed_at='2026-10-22T10:00:00+00:00',evidence_sha256='b'*64,
        task_outcome='COMPLETED',feedback='Synthetic tester found the renewal step; clarify the date label.',
        duration_seconds=42,consent=True,feature_ids=['renewal-report'])


class CustomerWorkflowTests(unittest.TestCase):
    def test_prototype_observation_time_requires_consent_valid_outcome_and_past_date(self):
        value = prototype()
        self.assertEqual(prototype_observation_time(value, OBSERVED), datetime.fromisoformat(value['observed_at']))
        for changes in (dict(consent=False), dict(task_outcome='PAID'), dict(observed_at='2999-01-01T00:00:00+00:00')):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                prototype_observation_time(dict(value, **changes), OBSERVED)

    def test_prototype_duration_preserves_unknown_and_rejects_malformed_values(self):
        for duration in (None, 0, 86400):
            self.assertEqual(prototype_duration(dict(prototype(), duration_seconds=duration)), duration)
        for duration in (True, -1, 86401, 0.5):
            with self.subTest(duration=duration), self.assertRaises(Invalid):
                prototype_duration(dict(prototype(), duration_seconds=duration))

    def test_prototype_feature_ids_require_distinct_saved_features(self):
        features = proposal()['features']
        self.assertEqual(prototype_feature_ids(prototype(), features), ['renewal-report'])
        for refs in ([], ['foreign'], ['renewal-report', 'renewal-report'], [1]):
            with self.subTest(refs=refs), self.assertRaises(Invalid):
                prototype_feature_ids(dict(prototype(), feature_ids=refs), features)

    def test_prototype_result_validates_observed_facts_without_demand_claims(self):
        for outcome in ('COMPLETED','PARTIAL','NOT_COMPLETED'):
            value=dict(proposal(),prototype_result=dict(prototype(),task_outcome=outcome))
            normalized=workflow_data(value,OBSERVED)
            self.assertEqual(normalized,value)
            self.assertFalse(workflow_readout(value,OBSERVED)['paid_behavior_verified'])
            value['prototype_result']['feature_ids'].clear()
            self.assertEqual(normalized['prototype_result']['feature_ids'],['renewal-report'])
        self.assertNotIn('prototype_result',workflow_data(proposal(),OBSERVED))
        for duration in (None,0,86400):
            self.assertEqual(workflow_data(dict(proposal(),prototype_result=dict(prototype(),duration_seconds=duration)),OBSERVED)['prototype_result']['duration_seconds'],duration)

    def test_prototype_result_rejects_unconsented_future_unlinked_and_private_observations(self):
        changes=[dict(consent=False),dict(consent=1),dict(observed_at='2999-01-01T00:00:00+00:00'),
            dict(feature_ids=[]),dict(feature_ids=['foreign']),dict(feature_ids=['renewal-report']*2),
            dict(duration_seconds=True),dict(duration_seconds=-1),dict(duration_seconds=86401),dict(duration_seconds=.5),
            dict(feedback='person@example.test'),dict(feedback='x'*501),dict(task_outcome='PAID'),dict(evidence_sha256='bad')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(Invalid):
                workflow_data(dict(proposal(),prototype_result=dict(prototype(),**change)),OBSERVED)
        with self.assertRaises(Invalid):workflow_data(dict(proposal(),prototype_result=None),OBSERVED)

    def test_workflow_data_and_workflow_readout_keep_hypothesis_and_exclusions(self):
        value = proposal()
        normalized = workflow_data(value, OBSERVED)
        self.assertEqual(normalized, value)
        result = workflow_readout(value, OBSERVED)
        self.assertEqual(result["status"], "HYPOTHESIS_READY_FOR_REVIEW")
        self.assertFalse(result["demand_verified"])
        self.assertFalse(result["paid_behavior_verified"])
        self.assertEqual(result["excluded_features"], value["excluded_features"])

    def test_feature_data_requires_existing_distinct_sources_and_test(self):
        feature = proposal()["features"][0]
        self.assertEqual(feature_data(feature, ["public-one"]), feature)
        for changes in ({"source_ids": []}, {"source_ids": ["absent"]}, {"source_ids": ["public-one", "public-one"]}, {"validation": ""}):
            with self.assertRaises(Invalid):
                feature_data(dict(feature, **changes), ["public-one"])

    def test_observation_data_rejects_generated_private_or_future_sources(self):
        source = proposal()["sources"][0]
        self.assertEqual(observation_data(source, OBSERVED), source)
        for changes in ({"evidence_type": "GENERATED"}, {"url": "https://localhost/private"}, {"content_sha256": "bad"},
                        {"observed_at": "2999-01-01T00:00:00+00:00"}):
            with self.assertRaises(Invalid):
                observation_data(dict(source, **changes), OBSERVED)
        with self.assertRaises(Invalid):
            public_excerpt("Contact private@example.com")

    def test_expired_or_removed_sources_stay_visible_and_block_linked_feature(self):
        value = proposal()
        value["sources"][0]["availability"] = "REMOVED"
        result = workflow_readout(value, OBSERVED)
        self.assertEqual(result["unavailable_source_ids"], ["public-one"])
        self.assertEqual(result["features"][0]["state"], "SOURCE_REVIEW_NEEDED")
        value["sources"][0]["availability"] = "AVAILABLE"
        value["sources"][0]["expires_at"] = "2026-10-02T00:00:00+00:00"
        self.assertEqual(workflow_readout(value, OBSERVED)["status"], "SOURCE_REVIEW_NEEDED")

    def test_bounded_rows_exclusion_data_and_duplicate_urls(self):
        self.assertEqual(exclusion_data({"feature": "CRM", "reason": "Unrelated"})["feature"], "CRM")
        with self.assertRaises(Invalid):
            bounded_rows([], 100, "sources")
        with self.assertRaises(Invalid):
            bounded_rows([{}] * 101, 100, "sources")
        value = proposal()
        value["sources"].append(dict(value["sources"][0], id="public-two"))
        with self.assertRaises(Invalid):
            workflow_data(value, OBSERVED)
        value = proposal()
        value["excluded_features"] = []
        with self.assertRaises(Invalid):
            workflow_data(value, OBSERVED)

    def test_pure_bounded_readout_preserves_original_without_network(self):
        value = proposal()
        before = copy.deepcopy(value)
        started = time.perf_counter()
        with patch("socket.socket") as network:
            for _ in range(100):
                workflow_readout(value, OBSERVED)
            network.assert_not_called()
        self.assertEqual(value, before)
        self.assertLess(time.perf_counter() - started, 5)
