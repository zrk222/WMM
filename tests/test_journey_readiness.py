"""Current coverage, validation and promotion boundaries with synthetic facts."""
import unittest
from copy import deepcopy
from mission_control.common import Invalid,now
from mission_control.journey_readiness import validate,result,complete,JOURNEYS
from mission_control.pipeline import current,kind_needs
from mission_control.creative_briefs import checked
from mission_control.service import validate_evidence
from tests.journey_fixtures import covered


class JourneyReadinessTests(unittest.TestCase):
    def test_complete_coverage_is_shared(self):
        data=covered();validate(data);self.assertTrue(complete(data));checked(data,'readiness')
        app={'data':{'release':'test-build','locale':'en-US'}}
        self.assertTrue(current({'kind':'readiness','data':data},app))
        for key in ('release','locale'):
            other=deepcopy(app);other['data'][key]='other'
            self.assertFalse(current({'kind':'readiness','data':data},other))

    def test_legacy_summaries_are_preserved_but_incomplete(self):
        data=dict(release='test-build',result='PASS',p0_count=0,device='synthetic',checked_at=now())
        validate_evidence('readiness',data,'synthetic')
        self.assertFalse(complete(data));self.assertEqual(result(data),'NOT_RUN')
        with self.assertRaises(Invalid):checked(data,'readiness')

    def test_failed_and_unrun_derive_status(self):
        for status in ('FAIL','NOT_RUN'):
            data=covered();data['journeys'][0]['status']=status;data['result']=status
            validate(data);self.assertEqual(result(data),status);self.assertFalse(complete(data))
            with self.assertRaises(Invalid):checked(data,'readiness')
        data=covered();data['p0_count']=1;data['result']='FAIL';validate(data);self.assertEqual(result(data),'FAIL')

    def test_invalid_shapes_and_contradictions(self):
        mutations=[lambda d:d.update(candidate_sha256='bad'),lambda d:d.update(journey_schema=True),
                   lambda d:d.update(locale=''),lambda d:d['journeys'].pop(),
                   lambda d:d['journeys'].append(d['journeys'][0]),
                   lambda d:d['journeys'][0].update(id='unknown'),
                   lambda d:d['journeys'][0].update(status={}),
                   lambda d:d['journeys'][0].update(expected=' '),
                   lambda d:d['journeys'][0].update(evidence=''),
                   lambda d:d['journeys'][0].update(observed=4),
                   lambda d:d['journeys'][0].update(reason='x'*2001),
                   lambda d:d['journeys'].__setitem__(1,deepcopy(d['journeys'][0])),
                   lambda d:d.update(result='FAIL')]
        for mutate in mutations:
            data=covered();mutate(data)
            with self.subTest(data=data):
                with self.assertRaises(Invalid):validate(data)

    def test_applicability_requires_reason_and_preserves_mandatory_checks(self):
        data=covered();data['journeys'][0].update(status='N/A',reason='This synthetic app has no accounts')
        validate(data);self.assertTrue(complete(data))
        data['journeys'][0]['reason']=''
        with self.assertRaises(Invalid):validate(data)
        for identity in ('core_value','devices','privacy','help_access'):
            data=covered();next(r for r in data['journeys'] if r['id']==identity).update(status='N/A',reason='Not tested')
            with self.assertRaises(Invalid):validate(data)

    def test_latest_incomplete_does_not_reuse_old_success(self):
        app={'data':{'release':'test-build','locale':'en-US'}}
        old=dict(kind='readiness',data=covered(),updated='2026-01-01')
        latest=deepcopy(old);latest['updated']='2026-02-01';latest['data']['journeys'][0]['status']='NOT_RUN';latest['data']['result']='NOT_RUN'
        self.assertTrue(kind_needs('readiness',app,[old,latest],[]))
        latest['data']={'release':'test-build','result':'PASS','p0_count':0}
        self.assertTrue(kind_needs('readiness',app,[old,latest],[]))

    def test_malformed_historical_records_never_pass(self):
        for rows in (None,{},['bad']*12):
            data=covered();data['journeys']=rows
            self.assertFalse(complete(data))
        data=covered();data['p0_count']=False;self.assertFalse(complete(data))


if __name__=='__main__':unittest.main()
