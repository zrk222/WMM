"""Fixed native PostHog setup and foreground refresh through shared Insights."""
import time
from .common import Invalid, identifier
from .ios_bridge import decode_document, encode_response


class NativeInsights:
    def __init__(self, service, identities, vault_callback):
        self.service = service
        self.identities = identities
        self.vault_callback = vault_callback

    def call(self, session, app_id, action, payload):
        from .credential_vault import namespace
        from .db import connection
        from .insights import Insights, bound_vault
        from .ios_provider_access import NativeVault
        from .operation_authority import bound_owner, protected
        body = decode_document(payload)
        identifier(app_id)
        fields = {'view': set(), 'refresh': {'id', 'confirm_read'},
                  'disconnect': {'id', 'version', 'confirm_disconnect'}, 'tick': set()}
        setup_fields = {'provider', 'project_id', 'region', 'api_key', 'automatic',
                        'confirm_read', 'dedicated_project', 'confirm_storage'}
        if not isinstance(body, dict):raise Invalid('Use a fixed native analytics action')
        if action == 'setup':
            if (set(body) - setup_fields - {'version', 'event_map'} or not setup_fields.issubset(body)
                    or body['provider'] != 'posthog' or body['confirm_storage'] is not True):
                raise Invalid('Confirm protected storage for a PostHog project')
        elif action not in fields or set(body) != fields[action]:
            raise Invalid('Use the exact fields for this native analytics action')
        user = self.identities.fresh(session)
        # Never bind API keys into the operation context or logs.
        envelope = dict(app_id=app_id, operation='native.insights.' + action,
                        input={} if action == 'setup' else body)
        prefix = 'AppGrowthInsights/' + namespace(self.service.store.path) + '/' + app_id + '/'
        insights = Insights(self.service.store)
        with bound_owner(self.service.store, envelope, self.identities, session, user):
            with protected(self.service.store, envelope):
                with bound_vault(self.service.store, app_id, lambda: NativeVault(self.vault_callback, prefix)):
                    if action == 'setup':
                        result = insights.setup(app_id, {key:value for key,value in body.items() if key != 'confirm_storage'})
                    elif action == 'view':
                        result = insights.list(app_id)
                        result['sources'] = [row for row in result['sources'] if row['provider'] == 'posthog']
                        result['reports'] = [row for row in result['reports'] if row['provider'] == 'posthog']
                        result['providers'] = {'posthog': result['providers']['posthog']}
                        result['execution'] = 'FOREGROUND_ONLY'
                    elif action in ('refresh', 'disconnect'):
                        with connection(self.service.store.path) as db:
                            source = insights.row(db, app_id, body['id'])
                            if source['provider'] != 'posthog':raise Invalid('Select this app’s PostHog source')
                        if action == 'refresh':
                            result = insights.refresh(app_id, body['id'], {'confirm_read':body['confirm_read']})
                        else:
                            result = insights.disconnect(app_id, body['id'],
                                {'version':body['version'], 'confirm_disconnect':body['confirm_disconnect']})
                    else:
                        with connection(self.service.store.path) as db:
                            stored = db.execute("SELECT * FROM insight_sources WHERE app_id=? AND provider='posthog'", (app_id,)).fetchone()
                            row = insights.row(db, app_id, stored['id']) if stored else None
                        due = (row and row['data']['automatic'] and row['next_due'] <= time.time()
                               and row['lease'] <= time.time()
                               and row['status'] not in ('DISCONNECTED', 'CLEANUP_REQUIRED', 'PERMISSION_REQUIRED'))
                        result = insights.refresh(app_id, row['id'], {'confirm_read':True}, automatic=True) if due else {'status':'IDLE'}
                        result['execution'] = 'FOREGROUND_ONLY'
        return encode_response(result)
