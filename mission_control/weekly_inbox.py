"""Bounded portfolio exceptions over saved workspaces; no external execution."""
from .common import Invalid, digest, now
from .weekly_controls import decision_controls

ROUTES = {'readiness': 'readiness', 'measurement': 'measurement', 'economics': 'results', 'retention': 'retention'}


def project(workspace):
    """Project only the selected app's evidence, not its credentials or conversations."""
    app = workspace['app']
    controls = decision_controls(app, workspace['records'], workspace['stages'])
    receipt = dict(app_id=app['id'], manifest_version=app['version'],
                   source_hash=controls['source_hash'], observed_at=now())
    cards = []
    for record in workspace['records']:
        if record['kind'] == 'review' and record['data'].get('confirmed') is True and record['data'].get('severity') == 'P0':
            cards.append(dict(id=digest([app['id'], record['id'], record['hash']]),
                category='critical', priority=0, state='NEEDS_REPAIR', title='Resolve confirmed critical finding',
                reason=record['title'], next_action='Investigate, repair and retest before acquisition.', resolution_route='findings'))
    for gate in controls['gates']:
        if gate['state'] != 'LOCAL_INPUTS_READY':
            stage = next((s for s in workspace['stages'] if s['id'] == gate['stage']), {})
            cards.append(dict(id=digest([app['id'], gate['id'], controls['source_hash']]),
                category=gate['id'], priority=gate['stage'], state=gate['state'], title=gate['id'].title()+' needs evidence',
                reason=(stage.get('missing') or ['Current source evidence is unavailable.'])[0],
                next_action=gate['next_action'], resolution_route=ROUTES[gate['id']]))
    for card in cards:
        card.update(app_id=app['id'], app_name=app['data']['name'], source_receipt=receipt,
                    change='NOT_COMPARED_WITH_PRIOR_REVIEW', cost_minor=None, owner='App operator')
    return dict(app_id=app['id'], app_name=app['data']['name'], source_receipt=receipt, exceptions=cards,
                local_ready=[g['id'] for g in controls['gates'] if g['state'] == 'LOCAL_INPUTS_READY'])


def review(service, offset=0):
    """Read at most five workspaces; retain every failed source and explicit coverage."""
    if type(offset) is not int or offset < 0:
        raise Invalid('Use a nonnegative portfolio offset')
    apps = service.store.apps()
    if offset > len(apps):
        raise Invalid('Portfolio changed; restart the weekly review')
    rows = []
    for app in apps[offset:offset+5]:
        try:
            row = project(service.workspace(app['id']))
        except Exception:
            row = dict(app_id=app['id'], app_name=app['data']['name'], local_ready=[],
                exceptions=[dict(id=digest([app['id'], 'unavailable']), app_id=app['id'], app_name=app['data']['name'],
                    priority=1, category='source', state='UNAVAILABLE', title='Workspace evidence unavailable',
                    reason='Saved evidence could not be evaluated. No success or zero result is inferred.',
                    next_action='Open this workspace and retry loading its saved evidence.', resolution_route='workspace',
                    source_receipt=dict(app_id=app['id'], manifest_version=app['version'], source_hash=None, observed_at=now()),
                    change='NOT_COMPARED_WITH_PRIOR_REVIEW', cost_minor=None, owner='App operator')])
        rows.append(row)
    return dict(schema='growth.weekly-exception-inbox.v1', observed_at=now(), apps=rows,
        exceptions=sorted([c for r in rows for c in r['exceptions']], key=lambda c:(c['priority'], c['app_id'])),
        coverage=dict(offset=offset, evaluated=len(rows), total_apps=len(apps), next_offset=offset+5 if offset+5<len(apps) else None),
        authority='NO_EXECUTION_AUTHORITY', spend_allowed=False, scale_allowed=False, learning_pilot_allowed=False,
        limits='Saved local evidence only. No prior-review comparison, independent outcome verification or campaign execution.')
