"""Native transport review conformance using the existing real owner/checker fixture."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.ios_operation_adapter import ScopedAgentAdapter
from tests import test_agent_review_dispatch as review_fixture
from tests import test_verified_review as identities


class IOSReviewedConformanceTests(unittest.TestCase):
    tearDown = review_fixture.ReviewedDispatchTests.tearDown
    setUp_base_policy = review_fixture.ReviewedDispatchTests.setUp_base
    body = review_fixture.ReviewedDispatchTests.body
    envelope = review_fixture.ReviewedDispatchTests.envelope
    listing_body = review_fixture.ReviewedDispatchTests.listing_body
    issue_reviewed = review_fixture.ReviewedDispatchTests.issue_reviewed
    approve = review_fixture.ReviewedDispatchTests.approve

    def setUp(self):
        # Reuse the isolated server/database and authenticated owner/checker fixture.
        self.setUp_base_policy()
        from mission_control.review_access import Access
        from mission_control.agent_checkpoints import Checkpoints
        Access(self.store).save('sample-one', identities.OWNER, identities.CHECKER,
            dict(login=identities.CHECKER['login'], role='CHECKER', status='ACTIVE', version=None))
        self.issued = self.issue_reviewed(); self.token = self.issued['token']
        self.adapter = ScopedAgentAdapter(self.server.service)
        self.checkpoints = Checkpoints(self.store)
        self.input = self.envelope('growth.save', self.listing_body())

    def prepare(self):
        return json.loads(self.adapter.prepare_review(self.token, 'review-one', json.dumps(self.input).encode()))

    def resume(self, approved):
        return json.loads(self.adapter.resume_review(self.token, 'sample-one', 'review-one', approved['revision'], approved['hash']))

    def test_approved_saved_input_executes_once(self):
        prepared = self.prepare()
        with self.assertRaises(Invalid):
            self.resume(prepared['checkpoint'])
        approved = self.approve(prepared)
        result = self.resume(approved)
        self.assertEqual(result['result']['outcome'], 'SUCCEEDED')
        with self.assertRaises(Invalid):
            self.resume(approved)

    def test_cancel_on_independent_control_request_keeps_unknown_receipt(self):
        approved = self.approve(self.prepare())
        def cancel_then_fail(service, envelope):
            def cancel():
                row = self.checkpoints.inspect('sample-one', 'review-one')
                self.checkpoints.cancel('sample-one', 'review-one', identities.OWNER['principal'], row['revision'])
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(cancel).result(timeout=5)
            raise RuntimeError('synthetic-private-sentinel')
        with patch('mission_control.operation_runtime.execute', side_effect=cancel_then_fail):
            result = self.resume(approved)
        self.assertEqual(result['checkpoint']['state'], 'CANCEL_REQUESTED')
        self.assertEqual(result['result']['outcome'], 'UNKNOWN')
        self.assertNotIn('synthetic-private-sentinel', str(result))

    def test_revocation_after_claim_denies_business_commit(self):
        from mission_control.growth_review_store import GrowthReviews
        approved = self.approve(self.prepare())
        original = GrowthReviews.save
        def revoke_then_save(reviews, app, body):
            self.grants.revoke('sample-one', identities.OWNER, dict(id=self.issued['grant']['id'], version=1))
            return original(reviews, app, body)
        with patch.object(GrowthReviews, 'save', revoke_then_save):
            result = self.resume(approved)
        self.assertEqual(result['result']['outcome'], 'FAILED')
