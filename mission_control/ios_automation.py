"""Fixed native owner standing controls; execution acceptance remains separate."""
from contextlib import contextmanager
from pathlib import Path

from .common import Invalid, digest
from .ios_bridge import decode_document, encode_response


# These are the only workflow operations inspected for this bounded adapter.
# A catalog change fails closed until the native compatibility review is updated.
NATIVE_WORKFLOWS = {
    'experiment_preparation': frozenset({
        'experiment.register', 'experiment.evaluate', 'experiment.action',
    }),
    'local_evidence': frozenset({
        'workspace.read', 'evidence.save', 'operations.read', 'growth.read',
        'growth.history', 'growth.save', 'customer.history', 'customer.save',
        'measurement.read', 'snapshot.export', 'cohort.define', 'events.import',
        'billing.save', 'funnel.list', 'funnel.review', 'funnel.read', 'funnel.save',
        'funnel.observations', 'funnel.import', 'funnel.report', 'packaging.history',
        'packaging.read', 'packaging.save', 'packaging.reconcile', 'packaging.checklist',
        'packaging.taste-read', 'packaging.taste-history', 'discovery.history',
        'discovery.read', 'discovery.review', 'discovery.collect', 'discovery.watch',
        'discovery.attempt', 'discovery.handoff',
    }),
}


def native_blockers(selection):
    from .automation_requirements import WORKFLOWS
    blockers = []
    for name in selection['workflows']:
        approved = NATIVE_WORKFLOWS.get(name)
        actual = WORKFLOWS.get(name, {}).get('operations', [])
        if approved is None or len(actual) != len(approved) or set(actual) != approved:
            reason = {'pipeline_preparation': 'NATIVE_STANDING_JOB_BINDING_REQUIRED',
                      'native_screen_render': 'NATIVE_SCREEN_RENDER_ADAPTER_REQUIRED'}.get(
                          name, 'NATIVE_WORKFLOW_ADAPTER_REQUIRED')
            blockers.append(dict(workflow=name, reason=reason))
    return blockers


@contextmanager
def native_access(service, identities, session, vault_callback):
    """Bind trusted Keychain and session checks to admission and job dispatch.

    The host wraps synchronous native calls; neither callback comes from JSON.
    Active policies from any other surface must satisfy the same native scope.
    """
    from .agent_access import AgentAccess, target
    from .complete_automation import bound_access_verifier, stored_object
    from .db import connection
    from .ios_provider_access import NativeProviderAccess, NativeVault
    user = identities.fresh(session)
    expected_store = Path(service.store.path).resolve()

    def verify(store, app_id, identity):
        identities.local(session, user['principal'], user['session_generation'])
        if Path(store.path).resolve() != expected_store:
            raise PermissionError('Native automation cannot cross its local datastore')
        with connection(store.path) as db:
            rows = db.execute("SELECT owner,proposal,summary,summary_hash FROM automation_policies WHERE app_id=? AND status='ACTIVE'", (app_id,)).fetchall()
            for row in rows:
                proposal, summary = stored_object(row['proposal']), stored_object(row['summary'])
                if (row['owner'] != user['principal'] or digest(summary) != row['summary_hash']
                        or proposal['selection']['agent_connection_id'] != identity
                        or native_blockers(proposal['selection'])):
                    raise PermissionError('Standing scope is not approved for native execution')
        prefix = target(store, app_id, 'placeholder').rsplit('/', 1)[0] + '/'
        access = AgentAccess(store, vault_factory=lambda: NativeVault(vault_callback, prefix))
        row = access.get(app_id, identity)
        if row['data'].get('provider') not in NativeProviderAccess.SUPPORTED:
            raise Invalid('Native standing controls require a supported protected HTTPS provider')
        if not access.secret(app_id, row):
            raise Invalid('Reconnect the protected key before activation')
        identities.local(session, user['principal'], user['session_generation'])

    with bound_access_verifier(verify, service.store):
        yield


class NativeAutomation:
    def __init__(self, service, identities, vault_callback):
        self.service = service
        self.identities = identities
        self.vault_callback = vault_callback

    def manage(self, session, app_id, action, payload):
        from .complete_automation import Automation, proposal_data, utc
        from .operation_authority import bound_owner, protected
        body = decode_document(payload)
        if not isinstance(body, dict) or action not in ('preview', 'activate', 'status', 'off'):
            raise Invalid('Choose a fixed native standing authority action')
        if action == 'status' and body:
            raise Invalid('Standing status accepts no body fields')
        if action == 'activate' and (set(body) != {'proposal', 'summary_hash', 'confirm_scope'} or body['confirm_scope'] is not True):
            raise Invalid('Confirm the exact standing scope')
        if action == 'off' and (set(body) != {'id', 'version', 'confirm_off'} or body['confirm_off'] is not True):
            raise Invalid('Confirm the exact standing approval revision to switch OFF')
        user = self.identities.fresh(session)
        envelope = dict(app_id=app_id, operation='native.automation.' + action, input=body)
        with bound_owner(self.service.store, envelope, self.identities, session, user):
            with protected(self.service.store, envelope):
                automation = Automation(self.service.store)
                if action in ('preview', 'activate'):
                    proposal = proposal_data(body if action == 'preview' else body['proposal'], utc())
                    blockers = native_blockers(proposal['selection'])
                    if blockers:
                        if action == 'activate':
                            raise Invalid('Selected workflow requires a native implementation and compatibility review')
                        return encode_response(dict(proposal=proposal, authority_issued=False,
                                                    native_readiness='BLOCKED', blockers=blockers))
                    if action == 'preview':
                        result = automation.preview(app_id, user, proposal)
                        result.update(native_readiness='READY_FOR_SCOPE_REVIEW', blockers=[], native_execution_acceptance='INCOMPLETE')
                    else:
                        with native_access(self.service, self.identities, session, self.vault_callback):
                            result = automation.activate(app_id, user, dict(proposal=proposal, summary_hash=body['summary_hash']))
                        result['native_execution_acceptance'] = 'INCOMPLETE'
                elif action == 'off':
                    result = automation.off(app_id, user, dict(id=body['id'], version=body['version']))
                else:
                    result = automation.status(app_id, user)
                    result['native_blockers'] = native_blockers(
                        {'workflows': list(result['catalog']['workflows'])})
                    result['native_execution_acceptance'] = 'INCOMPLETE'
                return encode_response(result)
