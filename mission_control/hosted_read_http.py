"""Finite authenticated private reads, independent of desktop HTTP and workers."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import secrets
import sqlite3

from .common import Invalid, canonical, digest
from .hosted_read_control import Unauthenticated, Unassigned
from .hosted_read_registry import RegistryUnavailable, exact_id

ROUTE = re.compile(r'/v1/tenants/([a-z0-9-]+)/clients/([a-z0-9-]+)/apps/([a-z0-9-]+)/dashboard')
COUNTS = frozenset(('queued', 'running', 'blocked', 'failed', 'succeeded',
                    'cancelled', 'unknown', 'interrupted', 'other'))


def validate_app(app, expected):
    """Validate only declared public app metadata."""
    if (not isinstance(app, dict) or set(app) != {'id', 'name', 'version'}
            or app['id'] != expected or not isinstance(app['name'], str)
            or len(app['name']) > 160 or type(app['version']) is not int
            or app['version'] < 1):
        raise Invalid('Dashboard projection is unavailable')


def validate_counts(counts):
    """Keep unrecognized job states inside a single explicit other counter."""
    if (not isinstance(counts, dict) or set(counts) != COUNTS
            or any(type(n) is not int or n < 0 for n in counts.values())):
        raise Invalid('Dashboard projection is unavailable')


def projection(value, tenant, client, app):
    """Reject an expanded domain response rather than subtract private fields."""
    if (not isinstance(value, dict) or set(value) != {'schema', 'app', 'jobs'}
            or value['schema'] != 'private-client-dashboard.v1'):
        raise Invalid('Dashboard projection is unavailable')
    validate_app(value['app'], app)
    validate_counts(value['jobs'])
    result = dict(value, tenant_id=tenant, client_id=client,
                  mode='PRIVATE_AUTHENTICATED_READ', effects_enabled=False)
    if len(canonical(result).encode('utf-8')) > 16384:
        raise Invalid('Dashboard projection is unavailable')
    return result


def request_token(headers):
    """Accept one opaque server-issued bearer; no identity claims or cookies."""
    authorization = headers.get('Authorization', '')
    if not re.fullmatch(r'Bearer wmmr_[A-Za-z0-9_-]{43}', authorization):
        raise Unauthenticated('Private read sign-in required')
    return authorization[7:]


def failure(error):
    """Project fixed status and reason codes without reflecting exception data."""
    kinds = ((Unauthenticated, 401, 'UNAUTHENTICATED'),
             ((Unassigned, KeyError), 404, 'UNASSIGNED'),
             (RegistryUnavailable, 503, 'REGISTRY_UNAVAILABLE'),
             ((sqlite3.Error, OSError), 503, 'CONTROL_UNAVAILABLE'))
    for kind, code, reason in kinds:
        if isinstance(error, kind):
            return code, reason
    return 503, 'PROJECTION_INVALID'


class ReadServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, control, registry):
        if address[0] != '127.0.0.1':
            raise Invalid('Private client reads may bind only to 127.0.0.1')
        self.control, self.registry = control, registry
        super().__init__(address, ReadHandler)


class ReadHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        return

    def send(self, code, body, receipt=None):
        raw = canonical(body).encode('utf-8')
        self.close_connection = True
        if self.request_version == 'HTTP/0.9':
            self.request_version = 'HTTP/1.0'
        self.send_response(code)
        for name, value in (('Content-Type', 'application/json; charset=utf-8'),
                            ('Content-Length', str(len(raw))), ('Cache-Control', 'no-store'),
                            ('X-Content-Type-Options', 'nosniff'), ('Connection', 'close'),
                            ('Referrer-Policy', 'no-referrer')):
            self.send_header(name, value)
        if receipt:
            self.send_header('X-WMM-Receipt', receipt)
        self.end_headers()
        try:
            if self.command != 'HEAD':
                self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # An authorization receipt never claims confirmed delivery.

    def send_error(self, code, message=None, explain=None):
        """Keep parser and unknown-method failures inside the JSON boundary."""
        self.send(405 if code == 501 else 400, {'error': 'Unsupported private read request'})

    def header_bounds(self):
        """Reject ambiguous framing before reading any client data."""
        if len(self.headers) > 32 or sum(len(k) + len(v) + 4 for k, v in self.headers.items()) > 8192:
            raise Invalid('Request headers exceed the private read boundary')
        for name in ('Host', 'Authorization', 'Origin', 'Content-Length'):
            if len(self.headers.get_all(name, [])) > 1:
                raise Invalid('Ambiguous request headers')
        forbidden = {'cookie', 'forwarded', 'transfer-encoding', 'x-user', 'x-tenant',
                     'x-subject', 'x-verified', 'cf-access-jwt-assertion'}
        if any(k.lower() in forbidden or k.lower().startswith('x-forwarded-') for k in self.headers):
            raise Invalid('Unsupported identity or forwarding header')
        if self.headers.get('Content-Length', '0') != '0':
            raise Invalid('Private dashboard reads have no request body')

    def boundary(self):
        """Accept one exact private origin and finite dashboard path grammar."""
        origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.header_bounds()
        if self.request_version not in ('HTTP/1.0', 'HTTP/1.1'):
            raise Invalid('Unsupported private read protocol')
        if self.headers.get('Host') != origin[7:]:
            raise Invalid('Use the exact private read address')
        if self.headers.get('Origin', origin) != origin:
            raise Invalid('Cross-origin read rejected')
        match = ROUTE.fullmatch(self.path)
        if len(self.path) > 512 or not match:
            raise Invalid('Unknown private dashboard route')
        return tuple(exact_id(v) for v in match.groups())

    def collect(self, token, tenant, client, app, correlation):
        """Collect from one immutable entry and commit current read authority."""
        admitted = self.server.control.admit(token, tenant, client)
        entry = self.server.registry.resolve(tenant, client)
        data = projection(entry.service.client_dashboard(app), tenant, client, app)
        self.server.registry.check(entry)
        receipt = self.server.control.finish(admitted, app, digest(data), correlation)
        return data, receipt

    def denied(self, error, token, tenant, client, app, correlation):
        """A failed receipt write prevents any successful client response."""
        code, reason = failure(error)
        try:
            receipt = self.server.control.denied(token, tenant, client, app, reason, correlation)
        except Exception:
            return self.send(503, {'error': 'Private read unavailable'})
        messages = {401: 'Private read sign-in required', 404: 'Client is unavailable'}
        return self.send(code, {'error': messages.get(code, 'Private read unavailable')}, receipt)

    def do_GET(self):
        """Never dispatch local desktop endpoints or trust client identity fields."""
        try:
            tenant, client, app = self.boundary()
        except Invalid:
            return self.send(400, {'error': 'Unsupported private read request'})
        token, correlation = '', secrets.token_hex(16)
        try:
            token = request_token(self.headers)
            data, receipt = self.collect(token, tenant, client, app, correlation)
        except Exception as error:
            return self.denied(error, token, tenant, client, app, correlation)
        return self.send(200, data, receipt)

    def unsupported(self):
        self.send(405, {'error': 'Private dashboard is read-only'})

    do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = unsupported
