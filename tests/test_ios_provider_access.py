"""Native vault seam with real shared profile records; no network or Keychain claim."""
import json
import unittest
from tests import test_ios_host as fixture
from tests.test_agent_access import body
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_provider_access import NativeVault


class NativeProviderTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def setup_access(self):
        self.runtime.create_workspace(self.session,self.creation())
        self.values={};self.calls=[]
        self.runtime.vault_callback=self.vault

    def vault(self, raw):
        request=json.loads(raw);self.calls.append(request)
        action=request['action'];target=request['target']
        if action=='put':self.values[target]=request['value']
        elif action=='delete':self.values.pop(target,None)
        value=self.values.get(target) if action=='get' else None
        return json.dumps(dict(ok=True,value=value)).encode()

    def call(self, action, data=None, app='new-app'):
        return json.loads(self.runtime.native_providers(self.session,app,action,json.dumps(data or {}).encode()))

    def save(self, profile=None):
        return self.call('save',dict(confirm_storage=True,profile=profile or body()))

    def test_shared_profile_is_protected_and_view_never_reads_or_discloses_key(self):
        self.setup_access();result=self.save()
        self.assertEqual(result['status'],'CONFIGURED_UNTESTED')
        self.assertEqual(len(self.values),1)
        calls=len(self.calls)
        view=self.call('view')
        self.assertEqual(len(self.calls),calls)
        self.assertTrue(view['profiles'][0]['data']['protected_key'])
        self.assertEqual(view['native_inference'],'NOT_RUN')
        self.assertNotIn(body()['api_key'],json.dumps(view))
        with connection(self.path) as db:
            rows=' '.join(str(tuple(row)) for row in db.execute('SELECT * FROM agent_connections'))
            audit=' '.join(str(tuple(row)) for row in db.execute('SELECT * FROM audit'))
        self.assertNotIn(body()['api_key'],rows+audit)

    def test_rotation_and_disconnect_remove_only_retired_keys(self):
        self.setup_access();self.save()
        old=list(self.values)
        profile=self.call('view')['profiles'][0]
        changed=body();changed.update(id=profile['id'],version=profile['version'],api_key='synthetic-rotated-0123456789')
        self.save(changed)
        self.assertEqual(len(self.values),1);self.assertNotEqual(list(self.values),old)
        current=self.call('view')['profiles'][0]
        result=self.call('disconnect',dict(id=current['id'],version=current['version'],confirm_disconnect=True))
        self.assertEqual(result['status'],'DISCONNECTED');self.assertEqual(self.values,{})
        self.assertEqual(self.call('cleanup')['remaining'],0)

    def test_confirmations_scope_and_desktop_subscription_routes_deny(self):
        self.setup_access()
        for data in (dict(confirm_storage=False,profile=body()),dict(confirm_storage=True,profile=body(),role='OWNER'),
                     dict(confirm_storage=True,profile=body('codex'))):
            with self.assertRaises(Invalid):self.call('save',data)
        with self.assertRaises(PermissionError):self.call('view',app='other')
        self.available=False
        with self.assertRaises(PermissionError):self.call('save',dict(confirm_storage=True,profile=body()))
        self.assertEqual(self.values,{})

    def test_failed_protected_storage_never_commits_a_profile(self):
        self.setup_access()
        self.runtime.vault_callback=lambda raw:b'{"ok":false,"value":null}'
        with self.assertRaises(Invalid):self.save()
        self.assertEqual(self.call('view')['profiles'],[])

    def test_native_vault_rejects_foreign_namespace_path_and_malformed_receipt(self):
        self.setup_access();adapter=NativeVault(self.vault,'AgentGrowth/synthetic/app/')
        for target in ('AgentGrowth/other/app/a','AgentGrowth/synthetic/app/../../x',
                       'AgentGrowth/synthetic/app/not-a-uuid'):
            with self.assertRaises(Invalid):adapter.get(target)
        self.assertEqual(self.calls,[])


if __name__ == '__main__':unittest.main()
