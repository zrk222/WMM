"""Real socket acceptance over two isolated synthetic client databases."""
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.hosted_read_control import Control
from mission_control.hosted_read_http import ReadServer
from mission_control.hosted_read_registry import Registry, RegistryUnavailable
from mission_control.service import Service
from mission_control.store import Store


class PrivateReadHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = 1000.0
        self.control = Control(self.root / 'control.sqlite', clock=lambda: self.now)
        self.services = {}
        for client, name in (('client-a', 'Alpha client'), ('client-b', 'Beta private sentinel')):
            store = Store(self.root / (client + '.sqlite'), seed=False)
            store.save_app('same-app', dict(name=name, audience='PRIVATE_PROFILE_SENTINEL'))
            with connection(store.path) as db:
                for i in range(1 if client == 'client-a' else 3):
                    db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                               (str(i), 'same-app', 'pipeline', '{"private":"SECRET_JOB"}', 'UNKNOWN', 'now', 'now', str(i)))
            self.services[('tenant', client)] = Service(store)
            self.control.register_client('tenant', client)
        self.registry = Registry(self.root, self.services, self.control.path)
        self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'VIEWER')
        self.control.set_member('issuer', 'bob', 'tenant', 'client-b', 'OWNER')
        self.alice = self.control.issue_session('issuer', 'alice')
        self.bob = self.control.issue_session('issuer', 'bob')
        self.start()

    def start(self):
        self.server = ReadServer(('127.0.0.1', 0), self.control, self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop()
        self.temp.cleanup()

    def request(self, client='client-a', token=None, path=None, method='GET', headers=None):
        headers = dict(headers or {})
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        http = HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            http.request(method, path or '/v1/tenants/tenant/clients/' + client + '/apps/same-app/dashboard', headers=headers)
            response = http.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            http.close()

    def test_all_roles_read_finite_projection_without_domain_authority(self):
        for role in ('OWNER', 'OPERATOR', 'REVIEWER', 'VIEWER'):
            self.control.set_member('issuer', role, 'tenant', 'client-a', role)
            token = self.control.issue_session('issuer', role)
            code, headers, raw = self.request(token=token)
            self.assertEqual(code, 200, raw)
            data = json.loads(raw)
            self.assertEqual(data['app'], dict(id='same-app', name='Alpha client', version=1))
            self.assertEqual(data['jobs']['unknown'], 1)
            self.assertFalse(data['effects_enabled'])
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn('X-WMM-Receipt', headers)
            for secret in ('SECRET_JOB', 'PRIVATE_PROFILE_SENTINEL', 'Beta private sentinel', token, str(self.root)):
                self.assertNotIn(secret, raw.decode())
            self.assertEqual(self.request(token=token, method='POST')[0], 405)
        receipts = self.control.receipts()
        self.assertEqual({r['role'] for r in receipts if r['outcome'] == 'ALLOWED'},
                         {'OWNER', 'OPERATOR', 'REVIEWER', 'VIEWER'})
        self.assertFalse(hasattr(self.server, 'runner'))
        self.assertFalse(hasattr(self.server, 'service'))

    def test_unsigned_cross_client_missing_app_and_local_cookie(self):
        self.assertEqual(self.request()[0], 401)
        self.assertEqual(self.request(token='wmmr_' + 'x' * 43)[0], 401)
        other = self.request(client='client-b', token=self.alice)
        missing = self.request(token=self.alice, path='/v1/tenants/tenant/clients/client-a/apps/missing/dashboard')
        self.assertEqual(other[0], 404)
        self.assertEqual(other[2], missing[2])
        self.assertEqual(self.request(token=self.alice, path='/v1/tenants/other/clients/client-a/apps/same-app/dashboard')[0], 404)
        self.assertNotIn(b'Beta private sentinel', other[2])
        self.assertEqual(self.request(headers={'Cookie': 'growth_session=local'})[0], 400)
        self.assertEqual(self.request(token=self.alice, path='/api/bootstrap')[0], 400)
        self.assertEqual(self.request(token=self.alice, path='/api/agent-operations/call', method='POST')[0], 405)
        self.assertEqual(self.request(token=self.alice, path='/api/apps/same-app/export')[0], 400)

    def test_route_origin_host_and_ambiguous_headers_are_rejected(self):
        route = '/v1/tenants/tenant/clients/client-a/apps/same-app/dashboard'
        for path in (route + '?path=anything', route.replace('same-app', '..'), route.replace('client-a', 'client%2da'), route + '/', route.replace('/apps/', '//apps/')):
            self.assertEqual(self.request(path=path, token=self.alice)[0], 400)
        for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}, {'X-User': 'alice'},
                        {'X-Forwarded-Host': 'trusted.example'}, {'Transfer-Encoding': 'chunked'}, {'Content-Length': '1'}):
            self.assertEqual(self.request(token=self.alice, headers=headers)[0], 400)
        self.assertEqual(self.request(token=self.alice, headers={f'X-Extra-{i}': 'v' for i in range(33)})[0], 400)
        wire = ('GET ' + route + ' HTTP/1.1\r\nHost: 127.0.0.1:' + str(self.server.server_port)
                + '\r\nAuthorization: Bearer ' + self.alice + '\r\nAuthorization: Bearer ' + self.bob + '\r\n\r\n')
        with socket.create_connection(self.server.server_address, timeout=5) as client:
            client.sendall(wire.encode())
            self.assertIn(b' 400 ', client.recv(4096).split(b'\r\n')[0])
        with self.assertRaises(Invalid):
            ReadServer(('0.0.0.0', 0), self.control, self.registry)

    def test_unknown_methods_and_parser_errors_remain_bounded_json(self):
        for method in ('TRACE', 'CONNECT', 'ARBITRARY'):
            code, headers, raw = self.request(method=method, token=self.alice)
            self.assertEqual(code, 405)
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
            self.assertEqual(set(json.loads(raw)), {'error'})
        with socket.create_connection(self.server.server_address, timeout=5) as client:
            client.sendall(b'GET / HTTP/invalid\r\nHost: evil\r\n\r\n')
            chunks = []
            while chunk := client.recv(4096):
                chunks.append(chunk)
            raw = b''.join(chunks)
            self.assertIn(b' 400 ', raw.split(b'\r\n')[0])
            self.assertIn(b'Cache-Control: no-store', raw)
            self.assertNotIn(b'<html', raw)
            self.assertEqual(set(json.loads(raw.split(b'\r\n\r\n', 1)[1])), {'error'})

    def test_revocation_during_collection_suppresses_response_then_reactivation_stays_denied(self):
        service = self.services[('tenant', 'client-a')]
        original = service.client_dashboard
        entered, release = threading.Event(), threading.Event()
        def paused(app):
            result = original(app)
            entered.set()
            self.assertTrue(release.wait(5))
            return result
        with patch.object(service, 'client_dashboard', paused), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.request, token=self.alice)
            self.assertTrue(entered.wait(5))
            self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'VIEWER', 'REVOKED')
            release.set()
            result = future.result(timeout=10)
        self.assertEqual(result[0], 404)
        self.assertNotIn(b'Alpha client', result[2])
        self.assertFalse(any(r['outcome'] == 'ALLOWED' for r in self.control.receipts()))
        self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'VIEWER')
        self.assertEqual(self.request(token=self.alice)[0], 404)
        self.assertEqual(self.request(token=self.control.issue_session('issuer', 'alice'))[0], 200)

    def test_receipt_failure_and_projection_expansion_fail_closed(self):
        with patch.object(self.control, 'finish', side_effect=sqlite3.OperationalError('PRIVATE_SQL')):
            code, _, raw = self.request(token=self.alice)
        self.assertEqual(code, 503)
        self.assertNotIn(b'PRIVATE_SQL', raw)
        self.assertFalse(any(r['outcome'] == 'ALLOWED' for r in self.control.receipts()))
        db = sqlite3.connect(self.control.path)
        try:
            db.execute("CREATE TRIGGER refuse_allowed BEFORE INSERT ON receipts WHEN NEW.outcome='ALLOWED' BEGIN SELECT RAISE(ABORT, 'PRIVATE_SQL'); END")
            db.commit()
            self.assertEqual(self.request(token=self.alice)[0], 503)
            db.execute('DROP TRIGGER refuse_allowed')
            db.commit()
        finally:
            db.close()
        service = self.services[('tenant', 'client-a')]
        original = service.client_dashboard('same-app')
        with patch.object(service, 'client_dashboard', return_value=dict(original, secret='PRIVATE_SENTINEL')):
            code, _, raw = self.request(token=self.alice)
        self.assertEqual(code, 503)
        self.assertNotIn(b'PRIVATE_SENTINEL', raw)
        with patch.object(service, 'client_dashboard', side_effect=RuntimeError('PRIVATE_SENTINEL')):
            self.assertEqual(self.request(token=self.alice)[0], 503)
        with patch.object(self.control, 'denied', side_effect=sqlite3.OperationalError('PRIVATE_SQL')):
            self.assertEqual(self.request()[0], 503)

    def test_restart_expiry_logout_and_concurrent_services(self):
        self.stop()
        self.control = Control(self.root / 'control.sqlite', clock=lambda: self.now)
        self.start()
        def one(index):
            client, token, expected = ('client-a', self.alice, 'Alpha client') if index % 2 else ('client-b', self.bob, 'Beta private sentinel')
            code, _, raw = self.request(client=client, token=token)
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(raw)['app']['name'], expected)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(one, range(12)))
        receipts = [r for r in self.control.receipts() if r['outcome'] == 'ALLOWED']
        self.assertEqual(len(receipts), 12)
        self.assertEqual({r['client_id'] for r in receipts}, {'client-a', 'client-b'})
        self.control.revoke_session(self.alice)
        self.assertEqual(self.request(token=self.alice)[0], 401)
        self.now += 900
        self.assertEqual(self.request(client='client-b', token=self.bob)[0], 401)

    def test_registry_alias_links_missing_replaced_and_control_collision(self):
        service = self.services[('tenant', 'client-a')]
        with self.assertRaises(Invalid):
            Registry(self.root, {('tenant', 'one'): service, ('tenant', 'two'): service}, self.control.path)
        with self.assertRaises(Invalid):
            Registry(self.root, {('tenant', 'one'): service}, service.store.path)
        with self.assertRaises(RegistryUnavailable):
            Registry(self.root / 'missing', self.services, self.control.path)
        alias = self.root / 'hard-link.sqlite'
        os.link(service.store.path, alias)
        try:
            second = self.services[('tenant', 'client-b')]
            with patch.object(second.store, 'path', alias):
                with self.assertRaises(Invalid):
                    Registry(self.root, self.services, self.control.path)
        finally:
            alias.unlink()
        with tempfile.TemporaryDirectory() as outside:
            outside_file = Path(outside) / 'outside.sqlite'
            outside_file.write_bytes(b'not opened')
            with patch.object(service.store, 'path', outside_file):
                with self.assertRaises(RegistryUnavailable):
                    Registry(self.root, {('tenant', 'one'): service}, self.control.path)
        path = service.store.path
        saved = path.with_suffix('.saved')
        path.rename(saved)
        self.assertEqual(self.request(token=self.alice)[0], 503)
        self.assertFalse(path.exists())
        path.write_bytes(b'not a database')
        self.assertEqual(self.request(token=self.alice)[0], 503)
        path.unlink()
        saved.rename(path)

        link = self.root / 'linked.sqlite'
        try:
            link.symlink_to(path)
        except OSError:
            # Windows without developer-mode privilege: link detection still has a direct fixture.
            with patch('mission_control.hosted_read_registry.stat.S_ISLNK', return_value=True):
                with self.assertRaises(RegistryUnavailable):
                    self.registry.check(self.registry.entries[('tenant', 'client-a')])
        else:
            with patch.object(service.store, 'path', link):
                with self.assertRaises(RegistryUnavailable):
                    Registry(self.root, {('tenant', 'one'): service}, self.control.path)
            link.unlink()


    def test_revocation_after_committed_authorization_does_not_retract_prepared_response(self):
        original = self.control.finish
        def finish_then_revoke(*args):
            receipt = original(*args)
            self.control.set_member('issuer', 'alice', 'tenant', 'client-a', 'VIEWER', 'REVOKED')
            return receipt
        with patch.object(self.control, 'finish', finish_then_revoke):
            self.assertEqual(self.request(token=self.alice)[0], 200)
        self.assertEqual(self.request(token=self.alice)[0], 404)
        self.assertEqual(sum(r['outcome'] == 'ALLOWED' for r in self.control.receipts()), 1)
    def test_readonly_projection_never_recreates_missing_store_and_counts_other(self):
        service = self.services[('tenant', 'client-a')]
        with connection(service.store.path) as db:
            db.execute("UPDATE jobs SET status='NEW_UNRECOGNIZED_STATE'")
        self.assertEqual(service.client_dashboard('same-app')['jobs']['other'], 1)
        path = service.store.path
        saved = path.with_suffix('.saved')
        path.rename(saved)
        with self.assertRaises(sqlite3.Error):
            service.client_dashboard('same-app')
        self.assertFalse(path.exists())
        saved.rename(path)

    @unittest.skipUnless(os.name == 'nt', 'Windows native legacy path alias')
    def test_native_windows_short_path_alias_preserves_canonical_isolation(self):
        import ctypes
        short_path = ctypes.windll.kernel32.GetShortPathNameW
        short_path.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
        short_path.restype = ctypes.c_uint
        def short(path):
            buffer = ctypes.create_unicode_buffer(32768)
            size = short_path(str(path), buffer, len(buffer))
            self.assertTrue(0 < size < len(buffer))
            return Path(buffer.value)
        service = self.services[('tenant', 'client-a')]
        original = service.store.path.resolve()
        with patch.object(service.store, 'path', short(original)):
            registry = Registry(self.root.resolve(), self.services, short(Path(self.control.path)))
            entry = registry.resolve('tenant', 'client-a')
            self.assertEqual(entry.path, original)
            registry.check(entry)
            with self.assertRaises(KeyError):
                registry.resolve('another-tenant', 'client-a')


if __name__ == '__main__':
    unittest.main()
