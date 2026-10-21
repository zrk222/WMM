"""Explain evidence prerequisites without granting campaign or budget authority."""
from .common import Invalid, digest

GATES = (
    (2, 'readiness', 'Repair and retest the advertised journey on this release.'),
    (3, 'measurement', 'Connect and verify the outcome and consent evidence.'),
    (4, 'economics', 'Reconcile mature cohort proceeds, costs and refunds.'),
    (10, 'retention', 'Collect a mature retained-value cohort with its eligible denominator.'),
)


def decision_controls(app, records, checklist):
    """Require closed stage states and scope; a READY stage is still local evidence."""
    from .automatic_preparation import check_scope
    check_scope(app, records, ())
    stages = {}
    for row in checklist:
        if not isinstance(row, dict) or type(row.get('id')) is not int:
            raise Invalid('Weekly stage evidence is malformed; reload this app')
        identity = row['id']
        if not 1 <= identity <= 12 or identity in stages or row.get('status') not in ('READY', 'BLOCKED'):
            raise Invalid('Weekly stage evidence is duplicated or unsupported; reload this app')
        stages[identity] = row
    gates = []
    for identity, name, repair in GATES:
        stage = stages.get(identity)
        state = 'UNKNOWN' if stage is None else ('LOCAL_INPUTS_READY' if stage['status'] == 'READY' else 'NEEDS_EVIDENCE_OR_REPAIR')
        gates.append(dict(id=name, stage=identity, state=state,
                          next_action='Inspect source evidence and current permissions.' if state == 'LOCAL_INPUTS_READY' else repair))
    source = dict(app=app, records=sorted((r['id'], r['version'], r['hash']) for r in records), stages=checklist)
    return dict(schema='growth.weekly-decision-controls.v1', app_id=app['id'],
                manifest_version=app['version'], source_hash=digest(source), gates=gates,
                exception_order=[g['id'] for g in gates if g['state'] != 'LOCAL_INPUTS_READY'],
                spend_allowed=False, scale_allowed=False, learning_pilot_allowed=False,
                authority='NO_EXECUTION_AUTHORITY',
                next_action='Resolve evidence exceptions, then review an exact bounded action. No spend or scale is authorized.',
                limits='Local input readiness is not independently verified retention, provider permission or a growth outcome.')
