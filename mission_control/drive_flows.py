"""Durable app-bound Drive consent lifecycle; token adoption is a separate reviewed step."""
import hashlib
import time
from .common import Invalid, canonical, now, uid
from .db import connection
from . import drive_auth as auth
from .drive_secrets import Secrets, reference, queue
from .drive_flow_contract import LIVE, decoded, request, source_guard, binding, summary


class Flows:
    def __init__(self, store, port=8765):
        auth.play_auth.loopback(port)
        self.store = store; self.port = port; self.secrets = Secrets(store)

    def flow(self, app_id, identity):
        """Resolve an exact app-owned private consent row."""
        self.store.app(app_id); reference(identity)
        with connection(self.store.path) as db:
            return decoded(db.execute('SELECT * FROM drive_flows WHERE app_id=? AND id=?', (app_id, identity)).fetchone())

    def start(self, app_id, body):
        """Protect candidate credentials before committing an official consent handoff."""
        self.store.app(app_id); body = request(body); self.expire(app_id)
        config = auth.configuration(body['client_json'])
        state, hashed, verifier = auth.fresh_state(); stamp = now()
        row = dict(id=uid(), app_id=app_id, manifest_version=body['manifest_version'],
            connection_id=body['connection_id'], connection_version=body['connection_version'],
            state_hash=hashed, expires=time.time() + 600,
            data=dict(port=self.port, client_id=config['client_id'], scope=auth.SCOPE),
            created=stamp, updated=stamp)
        with connection(self.store.path) as db:source_guard(db, row)
        uri = auth.authorization(config, self.port, state, verifier)
        ref = self.secrets.stage(app_id, dict(config, verifier=verifier, binding=binding(row)))
        try:self.persist(row, ref)
        except Exception:
            self.secrets.retire(app_id, ref)
            raise
        return dict(flow_id=row['id'], status='PENDING', expires=row['expires'],
                    authorization_url=uri, scope=auth.SCOPE, next_action='COMPLETE_OFFICIAL_FILE_SELECTION',
                    connected_account='UNCHANGED', browser='DEFAULT_SYSTEM_BROWSER')

    def persist(self, row, ref):
        """Serialize exact context, cardinality and secret attachment before insertion."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); source_guard(db, row)
            self.limits(db, row['app_id'])
            self.secrets.activate(db, row['app_id'], ref, binding(row), ['client_id', 'client_secret', 'verifier'])
            db.execute('INSERT INTO drive_flows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (row['id'], row['app_id'], row['manifest_version'], row['connection_id'], row['connection_version'],
                 row['state_hash'], ref, canonical(row['data']), 'PENDING', row['expires'], row['created'], row['updated'], None))

    def limits(self, db, app_id):
        """Retain history instead of pruning evidence to admit unlimited setup attempts."""
        total = db.execute('SELECT COUNT(*) FROM drive_flows WHERE app_id=?', (app_id,)).fetchone()[0]
        count = db.execute("SELECT COUNT(*) FROM drive_flows WHERE app_id=? AND status IN ('PENDING','EXCHANGING','AWAITING_ACCOUNT')", (app_id,)).fetchone()[0]
        if total >= 1000:raise Invalid('Drive consent history reached1000 entries; preserve an archive before further setup')
        if count >= 8:raise Invalid('Finish or cancel an active Drive selection before starting another')

    def claim(self, state):
        """Exactly one live callback claims the random proof before a token request."""
        state = auth.state_value(state); hashed = hashlib.sha256(state.encode()).hexdigest()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = decoded(db.execute('SELECT * FROM drive_flows WHERE state_hash=?', (hashed,)).fetchone())
            if row['status'] != 'PENDING':raise Invalid('Drive callback was already claimed or canceled; inspect its progress')
            self.guard(db, row)
            db.execute("UPDATE drive_flows SET status='EXCHANGING',updated=? WHERE id=? AND status='PENDING'", (now(), row['id']))
        row['status'] = 'EXCHANGING'
        return row

    def guard(self, db, row):
        """An original listener, live expiry and frozen app/connection context are required."""
        if row['expires'] <= time.time():raise Invalid('Drive consent expired; start a new selection')
        if row['data'].get('port') != self.port or row['data'].get('scope') != auth.SCOPE:
            raise Invalid('Drive listener or permission changed; prepare new consent')
        return source_guard(db, row)

    def alive(self, row):
        """Recheck cancellation, original proof and immutable context around external steps."""
        with connection(self.store.path) as db:
            current = decoded(db.execute('SELECT * FROM drive_flows WHERE app_id=? AND id=?', (row['app_id'], row['id'])).fetchone())
            if current['status'] != 'EXCHANGING' or binding(current) != binding(row):
                raise Invalid('Drive selection was stopped or changed; existing connection is preserved')
            self.guard(db, current)
        return current

    def pending(self, row):
        """Load only the original live flow's protected client and verifier."""
        current = self.alive(row)
        return self.secrets.load(current['app_id'], current['secret_ref'], binding(current))

    def stop(self, app_id, identity, status='CANCELLED'):
        """Terminalize and queue retirement atomically before attempting native removal."""
        if status not in ('CANCELLED', 'EXPIRED', 'UNCONFIRMED'):raise Invalid('Unsupported Drive consent recovery state')
        self.store.app(app_id); reference(identity)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = decoded(db.execute('SELECT * FROM drive_flows WHERE app_id=? AND id=?', (app_id, identity)).fetchone())
            if row['status'] in LIVE:
                db.execute('UPDATE drive_flows SET status=?,updated=?,result=? WHERE app_id=? AND id=?',
                    (status, now(), canonical(dict(next_action='RECONNECT', prior_connection='PRESERVED')), app_id, identity))
                queue(db, app_id, row['secret_ref'])
        if row['status'] in LIVE:self.secrets.retire(app_id, row['secret_ref'])
        return dict(status=self.flow(app_id, identity)['status'], prior_connection='PRESERVED')

    def expire(self, app_id):
        """Expired exchanges remain unconfirmed; no automatic token-code replay on restart."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = [dict(row) for row in db.execute("SELECT id,status FROM drive_flows WHERE app_id=? AND expires<=? AND status IN ('PENDING','EXCHANGING','AWAITING_ACCOUNT') ORDER BY expires LIMIT 8", (app_id, time.time()))]
        for row in rows:self.stop(app_id, row['id'], 'EXPIRED' if row['status'] == 'PENDING' else 'UNCONFIRMED')

    def status(self, app_id):
        """Return bounded redacted preparation progress and cleanup obligations only."""
        self.store.app(app_id); self.expire(app_id)
        with connection(self.store.path) as db:
            rows = [decoded(row) for row in db.execute('SELECT * FROM drive_flows WHERE app_id=? ORDER BY rowid DESC LIMIT 8', (app_id,))]
            count = db.execute('SELECT COUNT(*) FROM drive_retirements WHERE app_id=?', (app_id,)).fetchone()[0]
        return summary(rows, count)
