"""Real loopback owner policy controls with synthetic assets and identities."""
import json
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError

from mission_control.operator_client import OperatorClient, ClientError
from mission_control.server import Server
from mission_control.db import connection
from mission_control.common import uid
from tests import test_organic_video_policy as fixtures
from tests import test_verified_review as identities


class PolicyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.OrganicPolicyTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store = self.f.store
        def synthetic_owner(path, token):
            user = identities.synthetic_identity(path, token)
            return dict(user, principal=fixtures.OWNER['principal'], login=fixtures.OWNER['login'])
        self.mock = patch('mission_control.operator_identity.github_read', side_effect=synthetic_owner)
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.server = Server(('127.0.0.1', 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.owner = OperatorClient(self.origin)
        self.owner.bootstrap()
        self.owner.request('POST', '/api/identity/login', dict(token=identities.OWNER_TOKEN))
        self.base = '/api/apps/'+fixtures.APP+'/organic-video/'

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, action, body):
        return self.owner.request('POST', self.base+action, body)

    def test_owner_create_read_reserve_and_revoke_use_exact_domain_authority(self):
        policy = self.request('policy-create', dict(request_id=uid(), policy=self.f.policy))
        selected = dict(policy_id=policy['id'], policy_hash=policy['hash'])
        self.assertEqual(self.request('policy-read', selected), policy)
        reserve = self.f.reservation_body(policy)
        result = self.request('policy-reserve', reserve)
        self.assertEqual(self.request('policy-reserve', reserve), result)
        self.assertEqual(result['data']['status'], 'HELD')
        self.assertNotIn('access_token', json.dumps(result))
        self.assertEqual(self.request('policy-revoke', selected)['status'], 'REVOKED')
        with self.assertRaises(ClientError):
            self.request('policy-read', selected)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_generation_reservations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)

    def test_domain_validation_and_paths_cannot_widen_owner_authority(self):
        for action, body in (('policy-create', dict(request_id='bad', policy=dict(self.f.policy, max_posts=21))),
                             ('policy-create?x=1', {}), ('policy-create/', {}),
                             ('policy-execute', {}), ('policy-admit', dict(actor='forged'))):
            with self.subTest(action=action), self.assertRaises(ClientError):
                self.request(action, body)
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request('POST', self.base+'policy-create', dict(request_id='anonymous', policy=self.f.policy))

    def test_missing_csrf_and_bearer_cookie_mixture_are_rejected(self):
        body = dict(request_id='forged', policy=self.f.policy)
        raw = json.dumps(body).encode()
        for origin, csrf, bearer in ((self.origin, 'wrong', False), ('http://foreign.invalid', self.owner.csrf, False),
                                     (self.origin, self.owner.csrf, True)):
            headers = {'Origin':origin,'Content-Type':'application/json','X-CSRF-Token':csrf,
                       'Cookie':'; '.join(c.name+'='+c.value for c in self.owner.cookies)}
            if bearer:
                headers['Authorization'] = 'Bearer synthetic-bearer'
            request = Request(self.origin+self.base+'policy-create',data=raw,method='POST',headers=headers)
            with self.assertRaises(HTTPError) as error:
                self.owner.opener.open(request, timeout=10)
            error.exception.close()
        with connection(self.store.path) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='organic_video_policies'").fetchone())


if __name__ == '__main__':
    unittest.main()
