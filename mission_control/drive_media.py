"""Confirmed selected Drive originals enter the immutable library without reuse permission."""
from .common import Invalid, identifier
from .db import connection
from .drive_accounts import read_account
from .drive_account_contract import connection_binding
from .drive_connection_state import Connections
from .drive_secrets import reference
from .drive_media_contract import provenance
from . import drive_media_transport as transport
from .managed_media_store import Media, _upload_body


class Importer:
    def __init__(self, store, port=8765):
        self.store = store; self.connections = Connections(store, port); self.media = Media(store)

    def selected(self, app_id, body):
        """An import binds exact connection, app revision, selected file and request key."""
        identifier(app_id)
        keys = {'connection_id', 'connection_version', 'file_id', 'manifest_version', 'request_key'}
        if not isinstance(body, dict) or set(body) != keys:raise Invalid('Use the selected Drive import fields only')
        reference(body['connection_id'])
        if type(body['connection_version']) is not int or body['connection_version'] < 1:
            raise Invalid('Reload the current Drive connection revision')
        manifest, key = _upload_body({field: body[field] for field in ('manifest_version', 'request_key')})
        row = self.connections.row(app_id)
        if row is None or (row['id'], row['version']) != (body['connection_id'], body['connection_version']):
            raise Invalid('Drive connection changed; reload before importing')
        if not isinstance(body['file_id'], str) or body['file_id'] not in row['data']['selected_files']:
            raise Invalid('This file was not selected for the confirmed Drive account')
        if row['data']['manifest_version'] != manifest:raise Invalid('App setup changed; review Drive access again')
        self.guard(row)
        return row, dict(manifest_version=manifest, request_key=key)

    def guard(self, row):
        """Revocation, replacement, expiry or changed app stops in-flight source handling."""
        current = self.connections.row(row['app_id'])
        if current != row or self.connections.readiness(row) != 'CONNECTED':
            raise Invalid('Drive import access changed or expired; reconnect or select again')

    def import_file(self, app_id, body, alive=lambda: None):
        """Verify account and content before and after one exact selected-file download."""
        row, upload = self.selected(app_id, body)
        def check():
            alive(); self.guard(row)
        secret = self.connections.secrets.load(app_id, row['secret_ref'], connection_binding(row))
        bearer = secret['access_token']; check()
        self.account(row, bearer); check()
        before = transport.read_metadata(body['file_id'], bearer); check()
        raw = transport.download(before, bearer, check); check()
        after = transport.read_metadata(body['file_id'], bearer); check()
        if before != after:raise Invalid('Drive original changed during download; select the current file again')
        self.account(row, bearer); check()
        source = provenance(row, before)
        return self.media._ingest(app_id, before['filename'], raw, upload, check, source)

    def account(self, row, bearer):
        """A bearer returning a different account can never borrow saved source selection."""
        current = read_account(bearer)
        if current['permission_id'] != row['data']['account']['permission_id']:
            raise Invalid('Drive account identity changed; reconnect and confirm the account')
