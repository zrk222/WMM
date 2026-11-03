"""Exact owner gateway rejects extra authority and unsupported external effects."""
import json
from mission_control.common import Invalid
from mission_control.onesignal_setup_http import OneSignalSetupGateway
from tests.test_onesignal_setup import SetupTests, Identity
from tests.test_measurement_connectors import FakeVault
from tests.test_onesignal_transport import APP, KEY


class NativeIdentity(Identity):
    def fresh(self,session):return {'principal':'owner-1'}


class GatewayTests(SetupTests):
    def test_gateway_enforces_exact_fields_and_scoped_actions(self):
        gateway=OneSignalSetupGateway(self.store,NativeIdentity(),FakeVault,self.transport)
        def call(action,value):return json.loads(gateway.call('session','sample-one',action,json.dumps(value).encode()))
        with self.assertRaises(Invalid):call('send',{})
        with self.assertRaises(Invalid):call('save-key',{'kind':'app','key':KEY,'version':0,'principal':'owner-1'})
        self.assertEqual(call('save-key',{'kind':'app','key':KEY,'version':0})['state'],'KEY_SAVED_UNBOUND')
        self.assertEqual(call('read',{'selected_id':APP})[0]['id'],APP)
        self.assertNotIn(KEY,json.dumps(call('status',{})))
