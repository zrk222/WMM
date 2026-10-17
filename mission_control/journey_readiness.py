"""Inspectable operator-reported journey coverage, never test execution authority."""
import re
from .common import Invalid

JOURNEYS=('authentication','core_value','corrections','restoration','quota','billing',
          'privacy','help_access','devices','accessibility','voice','language')
REQUIRED=frozenset(('core_value','privacy','help_access','devices'))
STATUSES=frozenset(('PASS','FAIL','NOT_RUN','N/A'))


def row_text(row):
    """Bound typed observation text before interpreting the row status."""
    for key in ('expected','observed','evidence','reason'):
        value=row.get(key,'')
        if not isinstance(value,str) or len(value)>2000:
            raise Invalid('Journey '+key+': use text up to2000characters')


def row_applicability(row):
    """Absent capabilities need reasons; universal journeys always need tests."""
    if row['id'] in REQUIRED:raise Invalid('This journey cannot be marked N/A')
    if not row.get('reason','').strip():raise Invalid('Explain why this journey does not apply')


def row_valid(row):
    """Reject malformed rows and unsupported applicability claims."""
    if not isinstance(row,dict) or row.get('id') not in JOURNEYS:
        raise Invalid('Choose a known journey')
    status=row.get('status')
    if not isinstance(status,str) or status not in STATUSES:raise Invalid('Choose PASS, FAIL, NOT_RUN or N/A')
    row_text(row)
    if status in ('PASS','FAIL') and not all(row.get(k,'').strip() for k in ('expected','observed','evidence')):
        raise Invalid('Tested journeys need expected behavior, observed behavior and evidence')
    if status=='N/A':row_applicability(row)


def candidate_valid(data):
    """Require an explicit versioned candidate fingerprint and tested locale."""
    if type(data.get('journey_schema')) is not int or data['journey_schema']!=1:
        raise Invalid('Use journey checklist schema1')
    if not isinstance(data.get('candidate_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',data['candidate_sha256']):
        raise Invalid('Enter the tested artifact SHA256:64lowercase hexadecimal characters')
    if not isinstance(data.get('locale'),str) or not data['locale'].strip():raise Invalid('Enter the tested locale')


def matrix_valid(data):
    """Validate the complete bounded matrix and candidate identity."""
    candidate_valid(data)
    rows=data.get('journeys')
    if not isinstance(rows,list) or len(rows)!=len(JOURNEYS):raise Invalid('Record all12journey statuses')
    for row in rows:row_valid(row)
    if len({row['id'] for row in rows})!=len(JOURNEYS):raise Invalid('Record each journey once')


def derived(data):
    """Derive status from explicit observations, not a submitted summary."""
    if data.get('p0_count',0)>0 or any(row['status']=='FAIL' for row in data['journeys']):return 'FAIL'
    if any(row['status']=='NOT_RUN' for row in data['journeys']):return 'NOT_RUN'
    return 'PASS'


def validate(data):
    """Preserve legacy history but validate every supplied matrix before writes."""
    if 'journeys' not in data:return
    matrix_valid(data)
    if data.get('result')!=derived(data):raise Invalid('Summary result must match the journey checklist')


def result(data):
    """Legacy, malformed and incomplete coverage cannot become a readiness pass."""
    try:
        matrix_valid(data)
        return derived(data)
    except (Invalid,TypeError):return 'NOT_RUN'


def complete(data):
    """Return true only for complete accepted coverage and a matching summary."""
    return type(data.get('p0_count')) is int and data['p0_count']==0 and data.get('result')=='PASS' and result(data)=='PASS'
