"""Durable single-use Google consent, verified replacement and explicit cleanup recovery."""
import hashlib
import json
import re
import time
from . import play_auth
from .common import Invalid, canonical, digest, now, uid
from .credential_vault import Vault, namespace, target as vault_target
from .db import connection
from .play_contract import SCOPE, target
from .play_reports import read
from .store import audit, decode


def current(db, app_id):
    """Resolve at most one app-owned Google connection; ambiguity requires review."""
    records = [decode(r) for r in db.execute("SELECT * FROM records WHERE app_id=? AND kind='connection'", (app_id,))]
    matches = [r for r in records if r['data'].get('provider') == 'google_play']
    if len(matches) > 1:raise Invalid('Multiple Google Play bindings exist; review the app connection first')
    return matches[0] if matches else None


def source_guard(db, flow):
    """Recheck manifest and connection versions before adopting any consent result."""
    app = db.execute('SELECT version FROM apps WHERE id=?', (flow['app_id'],)).fetchone()
    if app is None or app['version'] != flow['manifest_version']:
        raise Invalid('App changed during Google consent; start a new connection')
    old = current(db, flow['app_id'])
    identity, version = (old['id'], old['version']) if old else (None, 0)
    if identity != flow['connection_id'] or version != flow['connection_version']:
        raise Invalid('Google Play connection changed; the existing connection is preserved')
    return old


def decoded_flow(row):
    """Internal flow references never appear in public status output."""
    if row is None:raise Invalid('Google consent is unavailable; start a new connection')
    result = dict(row); result['config'] = json.loads(result['config'])
    result['result'] = json.loads(result['result']) if result['result'] else None
    return result


class PlayConnections:
    def __init__(self, store, port=8765):
        self.store = store; self.port = port; self.scope = namespace(store.path)
        play_auth.loopback(port)

    def name(self, app, reference):
        """Credential lookup stays bound to database, app, provider and generated reference."""
        return vault_target(self.scope, app, 'google_play', reference)

    def retire(self, app, reference):
        """Persist retirement before deleting; unavailable native storage remains recoverable."""
        if not reference:return 'NO_KEY'
        with connection(self.store.path) as db:
            db.execute('INSERT INTO play_retirements VALUES(?,?,0) ON CONFLICT(app_id,reference) DO UPDATE SET eligible=0', (app, reference))
        try:Vault().delete(self.name(app, reference))
        except Invalid:return 'LOCAL_CLEANUP_PENDING'
        with connection(self.store.path) as db:
            db.execute('DELETE FROM play_retirements WHERE app_id=? AND reference=?', (app, reference))
        return 'LOCAL_KEY_REMOVED'

    def cleanup(self, app):
        """Retry only recorded local retirements; never revoke a provider grant implicitly."""
        self.store.app(app)
        with connection(self.store.path) as db:
            refs = [r[0] for r in db.execute('SELECT reference FROM play_retirements WHERE app_id=? AND eligible<=? LIMIT 20', (app, time.time()))]
        for reference in refs:self.retire(app, reference)
        with connection(self.store.path) as db:
            remaining = db.execute('SELECT COUNT(*) FROM play_retirements WHERE app_id=?', (app,)).fetchone()[0]
        return dict(status='LOCAL_CLEANUP_PENDING' if remaining else 'CLEAN', attempted=len(refs), remaining=remaining)

    def stage_secret(self, app, reference, value):
        """A crashed native write remains discoverable without retiring a live in-flight candidate."""
        with connection(self.store.path) as db:
            db.execute('INSERT INTO play_retirements VALUES(?,?,?)', (app, reference, time.time() + 900))
        try:Vault().put(self.name(app, reference), value)
        except Exception:self.retire(app, reference); raise

    def flow(self, app, identity):
        """Read an exact flow only from its owning app workspace."""
        self.store.app(app)
        with connection(self.store.path) as db:
            return decoded_flow(db.execute('SELECT * FROM play_flows WHERE app_id=? AND id=?', (app, identity)).fetchone())

    def status(self, app):
        """Expose no state hash, verifier, token, secret reference or private client configuration."""
        self.store.app(app)
        self.expire(app)
        with connection(self.store.path) as db:
            rows = [decoded_flow(r) for r in db.execute('SELECT * FROM play_flows WHERE app_id=? ORDER BY rowid DESC LIMIT 8', (app,))]
            pending = db.execute('SELECT COUNT(*) FROM play_retirements WHERE app_id=?', (app,)).fetchone()[0]
        return dict(flows=[{k: r[k] for k in ('id', 'config', 'status', 'expires', 'result', 'created', 'updated')} for r in rows],
                    cleanup_pending=pending, scope='Protected local login; provider access may expire and is verified by each read')

    def stop(self, app, identity, state='CANCELLED'):
        """Cancellation wins before adoption, including during an in-flight exchange."""
        if state not in ('CANCELLED', 'EXPIRED', 'UNCONFIRMED'):raise Invalid('Unsupported Google consent recovery')
        row = self.flow(app, identity)
        with connection(self.store.path) as db:
            changed = db.execute("UPDATE play_flows SET status=?,updated=?,result=? WHERE app_id=? AND id=? AND status IN ('PENDING','EXCHANGING')",
                (state, now(), canonical(dict(next_action='RECONNECT', prior_connection='PRESERVED')), app, identity)).rowcount
        if changed:self.retire(app, row['secret_ref'])
        return dict(status=self.flow(app, identity)['status'], prior_connection='PRESERVED')

    def expire(self, app):
        """Expired exchanges are unconfirmed, never automatically replayed after restart."""
        self.store.app(app)
        with connection(self.store.path) as db:
            rows = list(db.execute("SELECT id,status FROM play_flows WHERE app_id=? AND expires<=? AND status IN ('PENDING','EXCHANGING')", (app, time.time())))
        for row in rows:self.stop(app, row['id'], 'EXPIRED' if row['status'] == 'PENDING' else 'UNCONFIRMED')

    def client_config(self, app, body, old):
        """Reuse an existing protected client only inside its original app namespace."""
        if body['client_json']:return play_auth.installed_config(body['client_json'])
        if not old:raise Invalid('Select the Google Desktop client JSON to begin setup')
        secret = Vault().get(self.name(app, old['data']['credential_ref']))
        if not secret or secret.get('binding', {}).get('app_id') != app:
            raise Invalid('Protected Google client is unavailable; select its Desktop client JSON again')
        return play_auth.client(secret)

    def request(self, app, body):
        """Validate exact local target approval before preparing any external consent handoff."""
        fields = {'client_json', 'package_name', 'track', 'manifest_version', 'connection_id', 'connection_version', 'confirm_read'}
        if not isinstance(body, dict) or set(body) != fields or body['confirm_read'] is not True:
            raise Invalid('Approve the displayed package, track and Google read-access setup')
        if type(body['manifest_version']) is not int or type(body['connection_version']) is not int:
            raise Invalid('Reload this app before approving Google consent')
        selected = target({k: body[k] for k in ('package_name', 'track')})
        manifest = self.store.app(app)
        declared = manifest['data'].get('android_package')
        if declared and declared != selected['package_name']:
            raise Invalid('Selected Android package differs from this app manifest; review app setup first')
        frozen = dict(app_id=app, manifest_version=body['manifest_version'],
                      connection_id=body['connection_id'], connection_version=body['connection_version'])
        with connection(self.store.path) as db:old = source_guard(db, frozen)
        return selected, frozen, old

    def start(self, app, body):
        """Protect the PKCE candidate and retain the current connection until a verified read succeeds."""
        selected, frozen, old = self.request(app, body)
        self.expire(app); self.cleanup(app)
        config = self.client_config(app, body, old)
        state, hashed, verifier = play_auth.fresh_state(); identity, reference = uid(), uid()
        public = dict(selected, client_id=config['client_id'], port=self.port)
        pending = dict(config, verifier=verifier, binding=dict(app_id=app, flow_id=identity, config_hash=digest(public)))
        self.stage_secret(app, reference, pending)
        try:self.persist_start(frozen, identity, reference, hashed, public)
        except Exception:self.retire(app, reference); raise
        return dict(flow_id=identity, status='PENDING', expires=self.flow(app, identity)['expires'],
                    authorization_url=play_auth.authorization(config, self.port, state, verifier),
                    scope=SCOPE, provider_writes='NOT_AUTHORIZED', package_name=selected['package_name'], track=selected['track'])

    def persist_start(self, frozen, identity, reference, hashed, public):
        """Source guards and bounded active consent count share the insertion transaction."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); source_guard(db, frozen)
            count = db.execute("SELECT COUNT(*) FROM play_flows WHERE app_id=? AND status IN ('PENDING','EXCHANGING')", (frozen['app_id'],)).fetchone()[0]
            if count >= 8:raise Invalid('Finish or cancel an existing Google consent before starting another')
            db.execute('INSERT INTO play_flows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity, frozen['app_id'], frozen['manifest_version'], frozen['connection_id'], frozen['connection_version'],
                 hashed, reference, canonical(public), 'PENDING', time.time() + 600, now(), now(), None))
            db.execute('DELETE FROM play_retirements WHERE app_id=? AND reference=?', (frozen['app_id'], reference))
            audit(db, frozen['app_id'], 'play.consent_prepared', dict(flow_id=identity, package_name=public['package_name'], track=public['track']))

    def claim(self, state):
        """Consume a random state exactly once before any external token operation."""
        if not isinstance(state, str) or not re.fullmatch(r'play_[A-Za-z0-9_-]{43}', state):
            raise Invalid('Google callback state is invalid; start a new connection')
        hashed = hashlib.sha256(state.encode()).hexdigest()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = decoded_flow(db.execute('SELECT * FROM play_flows WHERE state_hash=?', (hashed,)).fetchone())
            if row['status'] != 'PENDING':raise Invalid('Google callback was already used or cancelled; inspect saved connection progress')
            self.guard(db, row)
            db.execute("UPDATE play_flows SET status='EXCHANGING',updated=? WHERE id=?", (now(), row['id']))
        row['status'] = 'EXCHANGING'; return row

    def guard(self, db, row):
        """Expiry, listener, manifest and prior connection are immutable during consent."""
        if row['expires'] <= time.time():raise Invalid('Google consent expired; reconnect')
        if row['config']['port'] != self.port:raise Invalid('Local callback port changed; reconnect')
        return source_guard(db, row)

    def alive(self, row):
        """Recheck the durable claim around each external operation and native staging step."""
        with connection(self.store.path) as db:
            latest = decoded_flow(db.execute('SELECT * FROM play_flows WHERE id=? AND app_id=?', (row['id'], row['app_id'])).fetchone())
            if latest['status'] != 'EXCHANGING':raise Invalid('Google consent was stopped; the prior connection is preserved')
            self.guard(db, latest)

    def pending(self, row):
        """A tampered public config cannot change the protected client's app or target."""
        secret = Vault().get(self.name(row['app_id'], row['secret_ref']))
        expected = dict(app_id=row['app_id'], flow_id=row['id'], config_hash=digest(row['config']))
        if not secret or secret.get('binding') != expected:
            raise Invalid('Protected Google consent proof is unavailable; reconnect')
        return secret

    def finish(self, body):
        """Only a verified scoped read can replace an existing protected login."""
        if not isinstance(body, dict) or set(body) not in ({'state', 'code'}, {'state', 'error'}):
            raise Invalid('Use the original Google consent callback without extra fields')
        row = self.claim(body['state'])
        try:
            if 'error' in body:raise Invalid('Google consent was declined; the existing connection is preserved')
            secret = self.pending(row); self.alive(row)
            grant = play_auth.exchange(secret, body['code'], secret['verifier'], row['config']['port'])
            self.alive(row)
            selected = {k: row['config'][k] for k in ('package_name', 'track')}
            report = read(selected, 'play_releases', play_auth.PlayReader(selected, grant['access_token']))
            self.alive(row)
            return self.activate(row, secret, grant, report)
        except Exception as exc:
            self.fail(row)
            if isinstance(exc, Invalid):raise
            raise Invalid('Google setup could not be verified; retry consent. The prior connection is preserved') from None

    def fail(self, row):
        """Never label a consumed or interrupted consent as a working connection."""
        with connection(self.store.path) as db:
            db.execute("UPDATE play_flows SET status='FAILED',result=?,updated=? WHERE id=? AND status='EXCHANGING'",
                (canonical(dict(next_action='RECONNECT', prior_connection='PRESERVED')), now(), row['id']))
        self.retire(row['app_id'], row['secret_ref'])

    def activate(self, row, config, grant, report):
        """Stage credentials before a final transactional source check and adoption."""
        reference = uid(); app = row['app_id']; selected = {k: row['config'][k] for k in ('package_name', 'track')}
        protected = dict(play_auth.client(config), refresh_token=grant['refresh_token'], scopes=grant['scopes'],
                         binding=dict(app_id=app, **selected, client_id=config['client_id']))
        self.stage_secret(app, reference, protected)
        try:result, old = self.commit(row, reference, report)
        except Exception:self.retire(app, reference); raise
        cleanup = self.after_commit(app, row['secret_ref'], old)
        return dict(status='CONNECTED', app_id=app, connection_id=result['connection_id'], observation=report, cleanup=cleanup)

    def after_commit(self, app, pending_ref, old):
        """A cleanup fault cannot turn an already committed connection into a false failed replacement."""
        try:
            result = self.retire(app, old['data'].get('credential_ref')) if old else 'NO_PRIOR_KEY'
            pending = self.retire(app, pending_ref)
            return 'LOCAL_CLEANUP_PENDING' if pending == 'LOCAL_CLEANUP_PENDING' else result
        except Exception:
            return 'LOCAL_CLEANUP_PENDING'

    def adopt_target(self, db, row):
        """Bind the approved Android target without changing the separate Apple Store identity."""
        saved = db.execute('SELECT data,version FROM apps WHERE id=?', (row['app_id'],)).fetchone()
        data = json.loads(saved['data'])
        fields = dict(android_package=row['config']['package_name'], android_track=row['config']['track'],
                      play_store_url='https://play.google.com/store/apps/details?id='+row['config']['package_name'])
        if all(data.get(k) == v for k, v in fields.items()):return saved['version']
        data.update(fields)
        db.execute('UPDATE apps SET data=?,version=version+1,updated=? WHERE id=? AND version=?',
                   (canonical(data), now(), row['app_id'], saved['version']))
        audit(db, row['app_id'], 'play.target_approved', dict(package_name=fields['android_package'], track=fields['android_track']))
        return saved['version'] + 1

    def commit(self, row, reference, report):
        """Cancellation or source drift wins before the active binding changes."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            latest = decoded_flow(db.execute('SELECT * FROM play_flows WHERE id=?', (row['id'],)).fetchone())
            if latest['status'] != 'EXCHANGING':raise Invalid('Google consent was cancelled before adoption')
            old = self.guard(db, latest); identity = old['id'] if old else uid()
            manifest_version=self.adopt_target(db, latest)
            public = dict(provider='google_play', auth_mode='managed_oauth', credential_ref=reference,
                account_id='ACCOUNT_NOT_READ', store_app_id=row['config']['package_name'],
                **{k: row['config'][k] for k in ('package_name', 'track', 'client_id')},
                scopes=[SCOPE], verified_at=report['observed_at'], verified_source_hash=report['source_hash'])
            self.store._write_record(db, row['app_id'], identity, 'connection', 'Google Play · ' + public['package_name'],
                'Official Google consent and scoped release verification', public, 'provider_read', old['version'] if old else None)
            result = dict(connection_id=identity, connection_version=old['version']+1 if old else 1,
                          manifest_version=manifest_version, observation=report, account_identity='NOT_READ')
            obsolete = [row['secret_ref']] + ([old['data']['credential_ref']] if old and old['data'].get('credential_ref') else [])
            for unused in obsolete:
                db.execute('INSERT INTO play_retirements VALUES(?,?,0) ON CONFLICT(app_id,reference) DO UPDATE SET eligible=0', (row['app_id'], unused))
            db.execute("UPDATE play_flows SET status='CONNECTED',result=?,updated=? WHERE id=?", (canonical(result), now(), row['id']))
            db.execute('DELETE FROM play_retirements WHERE app_id=? AND reference=?', (row['app_id'], reference))
        return result, old
