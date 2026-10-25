"""Private Drive connection state and exact-version local disconnect; no provider revocation."""
import time
from .common import Invalid, canonical, now
from .db import connection
from .drive_flows import Flows
from .drive_secrets import queue, reference
from .drive_account_contract import connection_row, connection_binding
from .drive_flow_contract import PERMISSION


class Connections:
    def __init__(self, store, port=8765):
        self.store = store; self.flows = Flows(store, port); self.secrets = self.flows.secrets

    def row(self, app_id):
        """Resolve only the selected app's private connection metadata."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            return connection_row(db.execute('SELECT * FROM drive_connections WHERE app_id=?', (app_id,)).fetchone())

    def status(self, app_id):
        """Report credential availability without exposing secrets or declaring reuse rights."""
        row = self.row(app_id)
        if row is None:return dict(status='SETUP_REQUIRED', permission_summary=PERMISSION, reuse_permission='NOT_GRANTED')
        status = self.readiness(row)
        current = self.row(app_id)
        if current != row:raise Invalid('Drive connection changed during status read; reload')
        return dict(id=row['id'], version=row['version'], status=status, account=row['data']['account'],
                    selected_files=row['data']['selected_files'], expires=row['expires'],
                    manifest_version=row['data']['manifest_version'], permission_summary=PERMISSION,
                    reuse_permission='NOT_GRANTED', provider_revocation='NOT_PERFORMED')

    def readiness(self, row):
        """Local connected metadata alone cannot certify usable protected access."""
        if row['status'] == 'DISCONNECTED':return 'DISCONNECTED'
        if row['status'] != 'CONNECTED':return 'RECONNECT_REQUIRED'
        if row['data']['manifest_version'] != self.store.app(row['app_id'])['version']:return 'APP_REVIEW_REQUIRED'
        if row['expires'] <= time.time():return 'ACCESS_EXPIRED'
        try:
            secret = self.secrets.load(row['app_id'], row['secret_ref'], connection_binding(row))
            if not {'access_token', 'refresh_token', 'client_id', 'client_secret'} <= set(secret):return 'RECONNECT_REQUIRED'
        except Invalid:return 'RECONNECT_REQUIRED'
        return 'CONNECTED'

    def disconnect(self, app_id, body):
        """Disable current access and pending replacements atomically before native cleanup."""
        keys = {'connection_id', 'version', 'confirm_disconnect'}
        if not isinstance(body, dict) or set(body) != keys or body['confirm_disconnect'] is not True:
            raise Invalid('Confirm disconnect for the displayed Drive account revision')
        reference(body['connection_id']); self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = connection_row(db.execute('SELECT * FROM drive_connections WHERE app_id=?', (app_id,)).fetchone())
            self.expected(row, body)
            pending = list(db.execute("SELECT id,secret_ref FROM drive_flows WHERE app_id=? AND status IN ('PENDING','EXCHANGING','AWAITING_ACCOUNT')", (app_id,)))
            refs = [item['secret_ref'] for item in pending]
            if row['secret_ref']:refs.append(row['secret_ref'])
            stamp = now()
            db.execute("UPDATE drive_connections SET status='DISCONNECTED',secret_ref=NULL,version=version+1,updated=? WHERE app_id=?", (stamp, app_id))
            db.execute("UPDATE drive_flows SET status='CANCELLED',updated=?,result=? WHERE app_id=? AND status IN ('PENDING','EXCHANGING','AWAITING_ACCOUNT')",
                       (stamp, canonical(dict(next_action='RECONNECT', prior_connection='DISCONNECTED_BY_OWNER')), app_id))
            for ref in refs:queue(db, app_id, ref)
        for ref in refs:self.secrets.retire(app_id, ref)
        return dict(status='DISCONNECTED', cleanup=self.cleanup_result(app_id), provider_revocation='NOT_PERFORMED', imported_media='PRESERVED')

    def cleanup_result(self, app_id):
        """Native-store lock cannot make disabled access appear connected or lose recovery."""
        try:return self.secrets.cleanup(app_id)
        except Invalid:
            with connection(self.store.path) as db:
                count = db.execute('SELECT COUNT(*) FROM drive_retirements WHERE app_id=?', (app_id,)).fetchone()[0]
            return dict(remaining=count, next_action='RETRY_LOCAL_CREDENTIAL_CLEANUP', provider_revocation='NOT_PERFORMED')

    def expected(self, row, body):
        """A stale disconnect cannot remove a replacement connection."""
        if row is None or row['id'] != body['connection_id']:
            raise Invalid('Drive connection changed; reload before disconnect')
        if type(body['version']) is not int or row['version'] != body['version']:
            raise Invalid('Drive connection revision changed; reload before disconnect')
