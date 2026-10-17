"""Synthetic checklist facts for tests only; never genuine app readiness."""
from mission_control.journey_readiness import JOURNEYS
from mission_control.common import now

def covered(release='test-build',locale='en-US',stamp=None):
    return dict(release=release,locale=locale,checked_at=stamp or now(),device='Synthetic Chromium',
                p0_count=0,result='PASS',journey_schema=1,candidate_sha256='a'*64,
                journeys=[dict(id=identity,status='PASS',expected='Synthetic expected behavior',
                               observed='Synthetic observed behavior',evidence='Synthetic test fixture only',reason='')
                          for identity in JOURNEYS])


def failed(data):
    from copy import deepcopy
    value=deepcopy(data);value['result']='FAIL';value['checked_at']=now()
    value['journeys'][0]['status']='FAIL'
    return value
