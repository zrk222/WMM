"""App-bound native Drive secret fields with recoverable staging and retirement."""
import hmac
import re
import time
import uuid
from .common import Invalid, identifier, uid
from .db import connection
from .credential_vault import Vault, namespace
from .play_auth import opaque

FIELDS = ('client_id', 'client_secret', 'verifier', 'access_token', 'refresh_token', 'binding')


def reference(value):
    """Only canonical opaque references may select a scoped native bundle."""
    try:
        if str(uuid.UUID(value)) != value:raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Invalid('Use the current Drive credential reference') from None
    return value


def binding(value):
    """The connection layer derives this digest from its exact flow and account context."""
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise Invalid('Drive credential binding is invalid; prepare a new connection')
    return value


def name(store, app_id, ref, field):
    """No arbitrary native credential address or cross-provider prefix is accepted."""
    identifier(app_id); reference(ref)
    if field not in FIELDS:raise Invalid('Unsupported protected Drive credential field')
    return '/'.join(('DriveMedia', namespace(store.path), app_id, ref, field))


def fields(value):
    """Freeze supported ASCII fields before registering or writing a candidate bundle."""
    if not isinstance(value, dict) or len(value) < 2 or set(value) - set(FIELDS):
        raise Invalid('Use supported protected Drive fields and their binding')
    binding(value.get('binding'))
    return {field: opaque(value[field], 'Drive credential') for field in FIELDS if field in value}


def queue(db, app_id, ref, delay=0):
    """Record only an app, opaque reference and one fixed recovery time in SQLite."""
    identifier(app_id); reference(ref)
    if type(delay) is not int or delay not in (0, 300):raise Invalid('Invalid Drive cleanup interval')
    db.execute('INSERT OR REPLACE INTO drive_retirements VALUES(?,?,?)', (app_id, ref, time.time() + delay))


def active(db, app_id, ref):
    """Pending consent and retained connection references protect against native deletion."""
    identifier(app_id); reference(ref)
    flow = db.execute("SELECT 1 FROM drive_flows WHERE app_id=? AND secret_ref=? AND status IN ('PENDING','EXCHANGING','AWAITING_ACCOUNT')", (app_id, ref)).fetchone()
    current = db.execute("SELECT 1 FROM drive_connections WHERE app_id=? AND secret_ref=? AND status!='DISCONNECTED'", (app_id, ref)).fetchone()
    return bool(flow or current)


class Secrets:
    def __init__(self, store):
        self.store = store

    def stage(self, app_id, value):
        """Register crash recovery before any native write; never persist the payload in SQL."""
        self.store.app(app_id); values = fields(value); ref = uid()
        with connection(self.store.path) as db:queue(db, app_id, ref, 300)
        try:
            vault = Vault()
            for field, secret in values.items():vault.put(name(self.store, app_id, ref, field), {'value': secret})
        except Exception:
            self.retire(app_id, ref)
            raise
        return ref

    def load(self, app_id, ref, expected_binding):
        """Return fields only after the caller's expected context matches protected binding."""
        self.store.app(app_id); reference(ref); binding(expected_binding)
        values = {}; vault = Vault()
        for field in FIELDS:
            value = vault.get(name(self.store, app_id, ref, field))
            if value is None:continue
            if not isinstance(value, dict) or set(value) != {'value'}:
                raise Invalid('Protected Drive credentials are invalid; reconnect')
            values[field] = opaque(value['value'], 'Drive credential')
        if not hmac.compare_digest(values.get('binding', ''), expected_binding):
            raise Invalid('Protected Drive credentials do not match this connection; reconnect')
        return values

    def activate(self, db, app_id, ref, expected_binding, required):
        """Caller attaches in this same transaction, serialized against retirement cleanup."""
        if not db.in_transaction:raise Invalid('Drive credential attachment needs its owning transaction')
        if not isinstance(required, (list, tuple)) or not required:
            raise Invalid('Declare the required Drive credential fields')
        if any(field not in FIELDS for field in required):raise Invalid('Unsupported required Drive credential field')
        if active(db, app_id, ref):raise Invalid('Protected Drive stage is already attached')
        pending = db.execute('SELECT eligible FROM drive_retirements WHERE app_id=? AND reference=?', (app_id, ref)).fetchone()
        if pending is None:raise Invalid('Protected Drive stage is unavailable; prepare it again')
        values = self.load(app_id, ref, expected_binding)
        if pending['eligible'] <= time.time():raise Invalid('Protected Drive stage expired; prepare it again')
        if not set(required) <= set(values):raise Invalid('Required protected Drive credentials are unavailable')
        db.execute('DELETE FROM drive_retirements WHERE app_id=? AND reference=?', (app_id, ref))

    def retire(self, app_id, ref):
        """Failed removal remains queued; active references always retain their credentials."""
        if not ref:return 'NO_PRIOR_SECRET'
        self.store.app(app_id); reference(ref)
        with connection(self.store.path) as db:queue(db, app_id, ref)
        try:
            self.clean_one(app_id, ref)
            return 'LOCAL_SECRET_REMOVED'
        except Invalid:
            return 'LOCAL_CLEANUP_REQUIRED'

    def clean_one(self, app_id, ref):
        """Remove only eligible inactive app-owned fields while retaining interrupted recovery."""
        identifier(app_id); reference(ref)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            pending = db.execute('SELECT eligible FROM drive_retirements WHERE app_id=? AND reference=?', (app_id, ref)).fetchone()
            if pending is None or pending['eligible'] > time.time():return
            if active(db, app_id, ref):raise Invalid('Cleanup cannot remove active Drive access')
            vault = Vault()
            for field in FIELDS:vault.delete(name(self.store, app_id, ref, field))
            db.execute('DELETE FROM drive_retirements WHERE app_id=? AND reference=?', (app_id, ref))

    def cleanup(self, app_id):
        """Bound each explicit recovery attempt to twenty eligible app-owned bundles."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            pending = [row['reference'] for row in db.execute('SELECT reference FROM drive_retirements WHERE app_id=? AND eligible<=? ORDER BY eligible,reference LIMIT 20', (app_id, time.time()))]
        for ref in pending:self.clean_one(app_id, ref)
        with connection(self.store.path) as db:
            remaining = db.execute('SELECT COUNT(*) FROM drive_retirements WHERE app_id=?', (app_id,)).fetchone()[0]
        return dict(remaining=remaining, provider_revocation='NOT_PERFORMED')
