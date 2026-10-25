"""Verified Drive consent exchange and explicit account adoption; no file download here."""
import hmac
import json
import time
from urllib.request import Request
from .common import Invalid, canonical, now, uid
from .db import connection
from . import drive_auth as auth
from .drive_flows import Flows
from .drive_flow_contract import decoded, binding
from .drive_secrets import queue
from .drive_account_contract import identity, packet, confirmation, connection_binding
from .payment_signature import unique_pairs
from .providers import report_bytes

ACCOUNT_ENDPOINT = 'https://www.googleapis.com/drive/v3/about?fields=user(permissionId,displayName,emailAddress,me,kind)'


def read_account(bearer):
    """One fixed projected GET; shared provider transport blocks credential redirects."""
    bearer = auth.play_auth.opaque(bearer, 'Drive access token')
    request = Request(ACCOUNT_ENDPOINT, headers={'Authorization': 'Bearer ' + bearer, 'Accept': 'application/json'}, method='GET')
    try:
        raw = report_bytes(request, 15)
        if len(raw) > 8192:raise ValueError('oversize')
        payload = json.loads(raw, object_pairs_hook=unique_pairs)
    except (Invalid, ValueError, TypeError, UnicodeError, RecursionError, OSError):
        raise Invalid('Drive account could not be verified; reconnect through Google') from None
    return identity(payload)


class Accounts:
    def __init__(self, store, port=8765):
        self.store = store; self.flows = Flows(store, port); self.secrets = self.flows.secrets

    def finish(self, query):
        """Claim once before exchange; failures never replay the code or replace an account."""
        fields = auth.callback(query); row = self.flows.claim(fields['state']); staged = None
        try:
            if 'error' in fields:return self.flows.stop(row['app_id'], row['id'])
            secret = self.flows.pending(row)
            grant = auth.exchange(secret, fields['code'], secret['verifier'], row['data']['port'])
            access_expires = time.time() + grant['expires_in']
            self.flows.alive(row); account = read_account(grant['access_token']); self.flows.alive(row)
            data = dict(row['data'], account=account, selected_files=fields['picked_file_ids'], access_expires=access_expires)
            candidate = dict(row, data=data)
            values = {key: secret[key] for key in ('client_id', 'client_secret')}
            values.update(access_token=grant['access_token'], refresh_token=grant['refresh_token'], binding=binding(candidate))
            staged = self.secrets.stage(row['app_id'], values)
            self.save_candidate(row, candidate, staged)
            self.secrets.retire(row['app_id'], row['secret_ref'])
            return self.review(row['app_id'], row['id'])
        except Exception:
            if staged:self.secrets.retire(row['app_id'], staged)
            self.flows.stop(row['app_id'], row['id'], 'UNCONFIRMED')
            raise Invalid('Drive consent could not be confirmed; existing connection is preserved. Start a new selection.') from None

    def save_candidate(self, original, candidate, ref):
        """Only the original live claim may attach a verified account candidate."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            self.current_claim(db, original)
            self.secrets.activate(db, original['app_id'], ref, binding(candidate), ['client_id', 'client_secret', 'access_token', 'refresh_token'])
            db.execute("UPDATE drive_flows SET status='AWAITING_ACCOUNT',data=?,secret_ref=?,updated=? WHERE id=?",
                       (canonical(candidate['data']), ref, now(), original['id']))
            queue(db, original['app_id'], original['secret_ref'])

    def current_claim(self, db, row):
        """Cancellation and public-context changes win before candidate attachment."""
        current = decoded(db.execute('SELECT * FROM drive_flows WHERE app_id=? AND id=?', (row['app_id'], row['id'])).fetchone())
        if current['status'] != 'EXCHANGING' or binding(current) != binding(row):
            raise Invalid('Drive consent stopped or changed before account verification')
        self.flows.guard(db, current)

    def reviewed(self, db, app_id, identity):
        """Use the same live source guards for review and adoption."""
        row = decoded(db.execute('SELECT * FROM drive_flows WHERE app_id=? AND id=?', (app_id, identity)).fetchone())
        self.flows.guard(db, row)
        return row, packet(row)

    def review(self, app_id, identity):
        """Account and selected-file review is private; protected values remain server-side."""
        self.store.app(app_id)
        with connection(self.store.path) as db:row, result = self.reviewed(db, app_id, identity)
        self.secrets.load(app_id, row['secret_ref'], binding(row))
        with connection(self.store.path) as db:
            _, fresh = self.reviewed(db, app_id, identity)
        if fresh['packet_hash'] != result['packet_hash']:raise Invalid('Drive account review changed; reload')
        return result

    def confirm(self, app_id, identity, body):
        """Restage with resulting connection authority before exact packet adoption."""
        expected = confirmation(body); self.store.app(app_id)
        with connection(self.store.path) as db:row, result = self.reviewed(db, app_id, identity)
        if not hmac.compare_digest(expected, result['packet_hash']):raise Invalid('Drive account review changed; reload before confirmation')
        secret = self.secrets.load(app_id, row['secret_ref'], binding(row))
        candidate = self.new_connection(row)
        values = {key: secret[key] for key in ('client_id', 'client_secret', 'access_token', 'refresh_token')}
        ref = self.secrets.stage(app_id, dict(values, binding=connection_binding(candidate)))
        try:retired = self.adopt(row, candidate, ref, expected)
        except Exception:
            self.secrets.retire(app_id, ref)
            raise
        for prior in retired:self.secrets.retire(app_id, prior)
        from .drive_connection_state import Connections
        return Connections(self.store, self.flows.port).status(app_id)

    def new_connection(self, row):
        """Connection identity stays stable on replacement while revision always increments."""
        data = dict(scope=auth.SCOPE, manifest_version=row['manifest_version'],
                    account=row['data']['account'], selected_files=row['data']['selected_files'])
        return dict(app_id=row['app_id'], id=row['connection_id'] or uid(), version=row['connection_version'] + 1,
                    data=data, expires=row['data']['access_expires'])

    def adopt(self, original, candidate, ref, expected):
        """Commit connection, terminal consent and retirements as one guarded transaction."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row, result = self.reviewed(db, original['app_id'], original['id'])
            if not hmac.compare_digest(expected, result['packet_hash']):raise Invalid('Drive review changed before adoption')
            old = db.execute('SELECT * FROM drive_connections WHERE app_id=?', (row['app_id'],)).fetchone()
            self.secrets.activate(db, row['app_id'], ref, connection_binding(candidate), ['access_token', 'refresh_token', 'client_id', 'client_secret'])
            stamp = now(); created = old['created'] if old else stamp
            db.execute('INSERT OR REPLACE INTO drive_connections VALUES(?,?,?,?,?,?,?,?,?)',
                (candidate['app_id'], candidate['id'], candidate['version'], canonical(candidate['data']), ref, 'CONNECTED', candidate['expires'], created, stamp))
            db.execute("UPDATE drive_flows SET status='CONFIRMED',result=?,updated=? WHERE id=?",
                       (canonical(dict(connection_id=candidate['id'], version=candidate['version'])), stamp, row['id']))
            retired = [row['secret_ref']]
            if old and old['secret_ref']:retired.append(old['secret_ref'])
            for prior in retired:queue(db, row['app_id'], prior)
        return retired
