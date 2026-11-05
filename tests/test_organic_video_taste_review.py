"""Delegated judgment validation with synthetic artifact/context and no providers."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch

from mission_control.common import Invalid, digest
from mission_control.creative_taste import guidance
from mission_control import organic_video_taste_review as taste
from tests import test_organic_video_policy as policy_fixture
from mission_control.agent_grants import Grants
from mission_control.hypit_jobs import HypitRenders
from mission_control.operation_authority import bound_agent, protected
from mission_control.organic_video_policy import Policies
from mission_control.db import connection


class TasteReviewTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.db.execute.return_value.fetchone.return_value = {'owner': 'owner'}
        self.current = patch.object(taste, 'current').start()
        self.addCleanup(patch.stopall)
        self.setting = dict(reviewer_grant_id='11111111-1111-4111-8111-111111111111', guidance_sha256=guidance()['policy_sha256'],
                            rules='Require readable captions and a demonstrated useful result.')
        self.saved = dict(hash='a'*64, created=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(),
                          data=dict(owner='owner', policy=dict(taste_auto_review=self.setting)))
        self.review = dict(policy_hash='a'*64, artifact_sha256='b'*64,
                           rules_sha256=digest(self.setting['rules']), guidance_sha256=self.setting['guidance_sha256'],
                           verdict='PASS', reviewed_at=datetime.now(timezone.utc).isoformat(),
                           checks=[dict(id=name, status='PASS', at_seconds=2,
                                        observation='Observed actual output at 2 seconds: '+name, fix='') for name in taste.CHECKS])
        self.output = dict(artifact_sha256='b'*64, taste_review=self.review)

    def run_review(self):
        taste.attest(self.db, 'app', self.saved, dict(grant_id='11111111-1111-4111-8111-111111111111'), self.output, 15)

    def test_selected_agent_pass_and_manual_compatibility(self):
        self.run_review()
        self.current.assert_called_once()
        args = self.current.call_args.args
        self.assertEqual(args[2], dict(app_id='app', operation='organic-video.policy-admit'))
        self.assertFalse(self.current.call_args.kwargs['check_quota'])
        taste.attest(self.db, 'app', dict(data=dict(policy={})), {}, {}, 15)

    def test_owner_cannot_forge_selected_agent_and_grant_failures_propagate(self):
        for context in ({'principal': 'owner'}, {'grant_id': 'other'}):
            with self.assertRaises(PermissionError):
                taste.attest(self.db, 'app', self.saved, context, self.output, 15)
        for reason in ('revoked', 'expired', 'wrong app', 'changed version'):
            self.current.side_effect = PermissionError(reason)
            with self.assertRaisesRegex(PermissionError, reason):
                self.run_review()

    def test_changed_guidance_rules_policy_and_artifact_reject(self):
        for key in ('policy_hash', 'artifact_sha256', 'rules_sha256', 'guidance_sha256'):
            old = self.review[key]
            self.review[key] = 'c'*64
            with self.assertRaises(Invalid):
                self.run_review()
            self.review[key] = old
        with patch.object(taste, 'guidance', return_value={'policy_sha256': 'd'*64}):
            with self.assertRaises(Invalid):
                self.run_review()

    def test_missing_unknown_or_critical_failure_never_passes(self):
        for verdict in ('REVISE', 'HOLD', 'UNKNOWN'):
            self.review['verdict'] = verdict
            with self.assertRaises(Invalid):
                self.run_review()
        self.review['verdict'] = 'PASS'
        original = deepcopy(self.review['checks'])
        for change in ({'status': 'FAIL'}, {'status': 'UNKNOWN'}, {'observation': '  '},
                       {'observation': 'x'*2001}, {'fix': 'x'*2001}, {'id': 'unknown'},
                       {'at_seconds': True}, {'at_seconds': -1}, {'at_seconds': 15},
                       {'at_seconds': float('nan')}, {'at_seconds': float('inf')}):
            self.review['checks'] = deepcopy(original)
            self.review['checks'][0].update(change)
            with self.assertRaises(Invalid):
                self.run_review()
        self.review['checks'] = original[:-1]
        with self.assertRaises(Invalid):
            self.run_review()

    def test_dates_setting_and_unknown_fields_are_closed(self):
        for date in ('invalid', '2000-01-01T00:00:00+00:00',
                     (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()):
            self.review['reviewed_at'] = date
            with self.assertRaises((Invalid, ValueError)):
                self.run_review()
        taste.setting(self.setting, 'STANDING_GENERATED')
        for value, mode in ((self.setting, 'EXACT'), (dict(self.setting, rules='  '), 'STANDING_GENERATED'),
                            (dict(self.setting, actor='owner'), 'STANDING_GENERATED')):
            with self.assertRaises(Invalid):
                taste.setting(value, mode)


class TastePolicyIntegrationTests(unittest.TestCase):
    """Real create/reserve/job/admit transactions and authenticated grant boundary."""
    setUp = policy_fixture.OrganicPolicyTests.setUp
    call = policy_fixture.OrganicPolicyTests.call
    create = policy_fixture.OrganicPolicyTests.create
    admission = policy_fixture.OrganicPolicyTests.admission
    reservation_body = policy_fixture.OrganicPolicyTests.reservation_body
    reserved_render = policy_fixture.OrganicPolicyTests.reserved_render
    render_artifact = policy_fixture.OrganicPolicyTests.render_artifact

    def prepared(self):
        version = self.store.app(policy_fixture.APP)['version']
        self.grants = Grants(self.store)
        self.issued = self.grants.issue(policy_fixture.APP, policy_fixture.OWNER, dict(
            agent_id='taste-reviewer', manifest_version=version, operations=['organic-video.policy-admit'],
            expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_calls=20))
        proposal = dict(self.policy, mode='STANDING_GENERATED', approved_output_hashes=[],
            taste_auto_review=dict(reviewer_grant_id=self.issued['grant']['id'],
                guidance_sha256=guidance()['policy_sha256'], rules='Actual controls readable; truthful payoff and usable CTA.'))
        saved = self.create(proposal)
        # Existing runtime fixture emits synthetic bytes. Give its validation receipt
        # the exact nested shape returned by hypit_media.validate_video, then retain
        # it through the normal job/attempt/artifact commit, not direct DB insertion.
        original_commit = HypitRenders.commit
        def validated_commit(renderer, job, folder, receipt):
            receipt['artifact']['metadata'] = dict(codec='h264', pixel_format='yuv420p',
                width=720, height=1280, frame_rate='24/1', duration_seconds=15.0,
                audio=False, audio_codec=None)
            return original_commit(renderer, job, folder, receipt)
        with patch.object(HypitRenders, 'commit', validated_commit):
            body = self.admission(saved)
        rules = saved['data']['policy']['taste_auto_review']
        body['output']['taste_review'] = dict(policy_hash=saved['hash'],
            artifact_sha256=body['output']['artifact_sha256'], rules_sha256=digest(rules['rules']),
            guidance_sha256=rules['guidance_sha256'], verdict='PASS',
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            checks=[dict(id=name, status='PASS', at_seconds=2.0,
                observation='Synthetic fixture observation for '+name, fix='') for name in taste.CHECKS])
        return saved, body

    def agent_admit(self, body):
        envelope = dict(app_id=policy_fixture.APP, operation='organic-video.policy-admit', input=body)
        admitted = self.grants.admit(self.issued['token'], envelope)
        with bound_agent(self.store, envelope, admitted):
            with protected(self.store, envelope):
                return Policies(self.store).admit(policy_fixture.APP, body)

    def test_real_policy_selected_agent_admits_nested_validation_receipt(self):
        saved, body = self.prepared()
        with self.assertRaises(PermissionError):
            self.call('admit', body)
        result = self.agent_admit(body)
        self.assertEqual(result['data']['output']['taste_review'], body['output']['taste_review'])
        self.assertEqual(result['data']['model_service_minor'], 0)
        self.assertEqual(saved['data']['taste_reviewer']['rules_sha256'],
                         body['output']['taste_review']['rules_sha256'])

    def test_real_policy_rejects_review_outside_decoded_duration_and_revoked_grant(self):
        saved, body = self.prepared()
        body['output']['taste_review']['checks'][0]['at_seconds'] = 15.0
        with self.assertRaisesRegex(Invalid, 'timestamps'):
            self.agent_admit(body)
        self.grants.revoke(policy_fixture.APP, policy_fixture.OWNER,
                           dict(id=self.issued['grant']['id'], version=self.issued['grant']['version']))
        with self.assertRaises(PermissionError):
            self.agent_admit(body)

    def test_real_policy_rejects_wrong_agent_and_changed_selected_grant_version(self):
        saved, body = self.prepared()
        selected = self.issued
        self.issued = self.grants.issue(policy_fixture.APP, policy_fixture.OWNER, dict(
            agent_id='another-reviewer', manifest_version=self.store.app(policy_fixture.APP)['version'],
            operations=['organic-video.policy-admit'],
            expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_calls=20))
        with self.assertRaisesRegex(PermissionError, 'owner-selected'):
            self.agent_admit(body)
        self.issued = selected
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_grants SET version=version+1 WHERE id=?', (selected['grant']['id'],))
        with self.assertRaisesRegex(PermissionError, 'version changed'):
            self.agent_admit(body)


if __name__ == '__main__':
    unittest.main()
