"""Native crypto/vault tests and synthetic provider lifecycle; no live credentials."""
import base64
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from urllib.parse import parse_qs
from mission_control.common import Invalid, uid
from mission_control.connection_setup import Connections, configuration
from mission_control.credential_vault import Vault, namespace, target
from mission_control.provider_auth import native, jwt, credential, CACHE, exchange
from mission_control.providers import credential as resolve
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once


def generated_key(curve="nistP256"):
    """Generate disposable key in process; never write or print a private key."""
    if sys.platform.startswith('linux'):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        key=ec.generate_private_key({'nistP256':ec.SECP256R1,'nistP384':ec.SECP384R1}[curve]())
        return key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode().strip()
    script=f"$k=[Security.Cryptography.ECDsa]::Create([Security.Cryptography.ECCurve+NamedCurves]::{curve}); try {{$k.ExportPkcs8PrivateKeyPem()}} finally {{$k.Dispose()}}"
    result=subprocess.run([shutil.which("pwsh"),"-NoProfile","-NonInteractive","-Command",script],capture_output=True,text=True,encoding="utf-8",timeout=10,creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError("Synthetic key generation failed")
    return result.stdout.strip()


class ProtectedSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key=generated_key()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/"test.sqlite")
        self.connections=Connections(self.store)
        self.config={"provider":"app_store","store_app_id":"123","issuer_id":"issuer-1","key_id":"KEY1","private_key":self.key}
        self.targets=[]
        CACHE.clear()

    def tearDown(self):
        for name in self.targets:
            Vault().delete(name)
        CACHE.clear()
        self.tmp.cleanup()

    def setup_key(self,body=None):
        result=self.connections.setup("sample-one",body or self.config)
        self.targets.append(self.connections.name("sample-one",result["record"]["data"]))
        return result["record"]

    def test_native_vault_and_signatures_are_real_and_cleanup(self):
        record=self.setup_key()
        name=self.targets[-1]
        self.assertEqual(Vault().get(name)["private_key"],self.key)
        token=jwt(configuration(self.config),1000)
        header,payload,signature=token.split(".")
        decode=lambda part:json.loads(base64.urlsafe_b64decode(part+"="*((-len(part))%4)))
        self.assertEqual(decode(header)["alg"],"ES256")
        self.assertEqual(decode(payload),{"iss":"issuer-1","iat":1000,"exp":1600,"aud":"appstoreconnect-v1"})
        public=native("inspect",self.key)["public_key"]
        if sys.platform.startswith('linux'):
            from cryptography.hazmat.primitives import serialization,hashes
            from cryptography.hazmat.primitives.asymmetric import ec,utils
            raw=base64.urlsafe_b64decode(signature+'==')
            der=utils.encode_dss_signature(int.from_bytes(raw[:32],'big'),int.from_bytes(raw[32:],'big'))
            serialization.load_pem_public_key(public.encode()).verify(der,(header+'.'+payload).encode(),ec.ECDSA(hashes.SHA256()))
            self.connections.disconnect('sample-one',record['id'],record['version'])
            self.assertIsNone(Vault().get(name))
            with self.assertRaisesRegex(Invalid,'disconnected'):resolve(self.store.records('sample-one')[0]['data'],'sample-one')
            return
        verify="$r=[Console]::In.ReadToEnd()|ConvertFrom-Json;$k=[Security.Cryptography.ECDsa]::Create();try{$k.ImportFromPem([string]$r.public_key);$k.VerifyData([Text.Encoding]::UTF8.GetBytes([string]$r.message),[Convert]::FromBase64String([string]$r.signature),[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.DSASignatureFormat]::IeeeP1363FixedFieldConcatenation)}finally{$k.Dispose()}"
        result=subprocess.run([shutil.which("pwsh"),"-NoProfile","-Command",verify],input=json.dumps({"public_key":public,"message":header+"."+payload,"signature":base64.b64encode(base64.urlsafe_b64decode(signature+"==")).decode()}),capture_output=True,text=True,timeout=10,creationflags=0x08000000)
        self.assertEqual(result.stdout.strip(),"True")
        self.connections.disconnect("sample-one",record["id"],record["version"])
        self.assertIsNone(Vault().get(name))
        with self.assertRaisesRegex(Invalid,"disconnected"):
            resolve(self.store.records("sample-one")[0]["data"],"sample-one")

    def test_native_rejects_public_wrong_curve_and_has_no_helper_process(self):
        public=native("inspect",self.key)["public_key"]
        for value in (public,generated_key("nistP384"),"not-a-key"):
            with self.assertRaises(Invalid) as error:
                native("inspect",value)
            self.assertNotIn(value,str(error.exception))
        with patch("subprocess.run",side_effect=AssertionError("Native runtime must not spawn a helper")):
            self.assertIn("PUBLIC KEY",native("inspect",self.key)["public_key"])

    def test_rotation_conflict_and_failed_commit_preserve_old_secret(self):
        first=self.setup_key()
        body={**self.config,"id":first["id"],"version":first["version"]}
        second=self.setup_key(body)
        self.assertIsNone(Vault().get(self.targets[0]))
        self.assertIsNotNone(Vault().get(self.targets[1]))
        with self.assertRaisesRegex(Invalid,"changed"):
            self.connections.setup("sample-one",body)
        created=[]
        real_put=Vault.put
        def put(vault,name,value):
            created.append(name);return real_put(vault,name,value)
        with patch.object(Vault,"put",put),patch.object(self.store,"save_record",side_effect=Invalid("synthetic commit failure")):
            with self.assertRaisesRegex(Invalid,"commit failure"):
                self.connections.setup("sample-one",{**body,"version":second["version"]})
        self.assertIsNone(Vault().get(created[0]))
        self.assertIsNotNone(Vault().get(self.targets[1]))

    def test_app_provider_database_scope_snapshot_and_secret_rejection(self):
        record=self.setup_key()
        binding={**record["data"],"_vault_namespace":namespace(self.store.path)}
        for app,changed in (("sample-two",{}),("sample-one",{"provider":"apple_ads"}),("sample-one",{"_vault_namespace":namespace(Path(self.tmp.name)/"other.sqlite")})):
            with self.assertRaisesRegex(Invalid,"missing"):
                credential({**binding,**changed},app)
        snapshot=self.store.export("sample-one")
        workspace=Service(self.store).workspace("sample-one")
        serialized=json.dumps([snapshot,workspace,self.store.history("sample-one")])
        self.assertNotIn(self.key,serialized)
        self.assertNotIn("PRIVATE KEY",serialized)
        restored=Store(Path(self.tmp.name)/"other.sqlite",seed=False)
        restored.restore(snapshot)
        self.assertEqual(Connections(restored).statuses("sample-one")[record["id"]]["status"],"RECONNECT_REQUIRED")
        for secretfield in ("private_key","client_secret","key_pem"):
            with self.assertRaises(Invalid):
                self.store.save_record("sample-one",{"kind":"connection","title":"bad","source":"synthetic","data":{**record["data"],secretfield:self.key}})

    def test_renewal_cache_expiry_missing_key_and_ads_claims(self):
        record=self.setup_key({**self.config,"provider":"apple_ads","account_id":"456","client_id":"SEARCHADS.client"})
        binding={**record["data"],"_vault_namespace":namespace(self.store.path)}
        observed=[]
        def mint(config,client_secret):
            payload=json.loads(base64.urlsafe_b64decode(client_secret.split(".")[1]+"=="))
            observed.append(payload)
            return "synthetic-token-"+str(len(observed)),3600
        with patch("mission_control.provider_auth.time.time",return_value=1000),patch("mission_control.provider_auth.exchange",side_effect=mint):
            self.assertEqual(credential(binding,"sample-one"),"synthetic-token-1")
            self.assertEqual(credential(binding,"sample-one"),"synthetic-token-1")
        with patch("mission_control.provider_auth.time.time",return_value=4541),patch("mission_control.provider_auth.exchange",side_effect=mint):
            self.assertEqual(credential(binding,"sample-one"),"synthetic-token-2")
        self.assertEqual(observed[0]["sub"],"SEARCHADS.client")
        self.assertEqual(observed[0]["aud"],"https://appleid.apple.com")
        self.assertEqual(observed[0]["exp"]-observed[0]["iat"],3600)
        Vault().delete(self.targets[-1])
        with self.assertRaisesRegex(Invalid,"missing"):credential(binding,"sample-one")
        self.assertFalse(CACHE)

    def test_fixed_token_exchange_limits_and_redacted_failures(self):
        response=MagicMock();response.read.return_value=json.dumps({"token_type":"Bearer","scope":"searchadsorg","access_token":"synthetic","expires_in":3600}).encode()
        opener=MagicMock();opener.open.return_value.__enter__.return_value=response
        with patch("mission_control.provider_auth.build_opener",return_value=opener):
            self.assertEqual(exchange({"client_id":"client"},"synthetic-secret"),("synthetic",3600))
        request=opener.open.call_args.args[0]
        self.assertEqual(request.full_url,"https://appleid.apple.com/auth/oauth2/token")
        self.assertEqual(request.method,"POST")
        self.assertEqual(parse_qs(request.data.decode())["client_secret"],["synthetic-secret"])
        self.assertEqual(opener.open.call_args.kwargs["timeout"],15)
        for payload in ([{}],{"token_type":"Bearer","scope":"wrong"},{"token_type":"Bearer","scope":"searchadsorg","access_token":"bad\r\nHeader","expires_in":3600},{"token_type":"Bearer","scope":"searchadsorg","access_token":"valid","expires_in":True}):
            response.read.return_value=json.dumps(payload).encode()
            with patch("mission_control.provider_auth.build_opener",return_value=opener),self.assertRaises(Invalid):
                exchange({"client_id":"client"},"synthetic-secret")
        opener.open.side_effect=HTTPError("fixed",403,self.key,None,None)
        with patch("mission_control.provider_auth.build_opener",return_value=opener),self.assertRaises(Invalid) as error:
            exchange({"client_id":"client"},"synthetic-secret")
        self.assertNotIn(self.key,str(error.exception))

    def test_managed_report_job_uses_runtime_scope_and_excludes_bearer(self):
        record=self.setup_key()
        service=Service(self.store)
        job=service.queue("sample-one",{"action":"sync","request_key":"managed-read","data":{"connection_id":record["id"]}})
        with patch("mission_control.providers.read_json",return_value={"data":{"id":"123"}}) as network:
            run_once(self.store)
        result=service.workspace("sample-one")["jobs"][0]
        self.assertEqual(result["status"],"SUCCEEDED")
        self.assertTrue(network.call_args.args[1]["Authorization"].startswith("Bearer ey"))
        self.assertNotIn("Bearer ey",json.dumps(result))

    def test_disconnect_commit_failure_preserves_binding_key_and_cache(self):
        record=self.setup_key()
        name=self.targets[-1]
        CACHE[name]=('synthetic-cached-bearer',9999999999)
        before=self.store.records('sample-one')
        with patch.object(self.store,'save_record',side_effect=Invalid('synthetic disconnect commit failure')),patch.object(Vault,'delete') as deletion:
            with self.assertRaisesRegex(Invalid,'commit failure'):
                self.connections.disconnect('sample-one',record['id'],record['version'])
            deletion.assert_not_called()
        self.assertEqual(self.store.records('sample-one'),before)
        self.assertEqual(Vault().get(name)['private_key'],self.key)
        self.assertEqual(CACHE[name],('synthetic-cached-bearer',9999999999))

    def test_disconnect_cleanup_failure_is_disabled_redacted_and_retryable(self):
        record=self.setup_key()
        name=self.targets[-1]
        CACHE[name]=('synthetic-cached-bearer',9999999999)
        with patch.object(Vault,'delete',side_effect=Invalid(self.key)):
            result=self.connections.disconnect('sample-one',record['id'],record['version'])
        self.assertEqual(result['status'],'DISCONNECTED')
        self.assertEqual(result['cleanup'],'PRIOR_LOCAL_KEY_CLEANUP_REQUIRED')
        self.assertNotIn(self.key,json.dumps(result))
        self.assertNotIn(name,CACHE)
        current=self.connections.record('sample-one',record['id'])
        self.assertEqual(current['data']['auth_mode'],'disconnected')
        with self.assertRaisesRegex(Invalid,'disconnected'):
            resolve(current['data'],'sample-one')
        self.assertIsNotNone(Vault().get(name))
        result=self.connections.disconnect('sample-one',record['id'],current['version'])
        self.assertEqual(result['cleanup'],'PRIOR_LOCAL_KEY_REMOVED')
        self.assertIsNone(Vault().get(name))

    def test_disconnect_commits_before_retiring_key_and_denies_stale_scope(self):
        record=self.setup_key()
        name=self.targets[-1]
        CACHE[name]=('synthetic-cached-bearer',9999999999)
        with patch.object(Vault,'delete') as deletion:
            for app,version in [('sample-two',record['version']),('sample-one',record['version']+1)]:
                with self.assertRaises(Invalid):
                    self.connections.disconnect(app,record['id'],version)
            deletion.assert_not_called()
        real_delete=Vault.delete
        def observe(vault,selected_name):
            self.assertEqual(self.connections.record('sample-one',record['id'])['data']['auth_mode'],'disconnected')
            self.assertNotIn(name,CACHE)
            return real_delete(vault,selected_name)
        with patch.object(Vault,'delete',observe):
            result=self.connections.disconnect('sample-one',record['id'],record['version'])
        self.assertEqual(result,{'status':'DISCONNECTED','provider_revocation':'NOT_PERFORMED','cleanup':'PRIOR_LOCAL_KEY_REMOVED'})

    def test_disconnected_cleanup_status_survives_reload_without_secret_disclosure(self):
        record=self.setup_key()
        with patch.object(Vault,'delete',side_effect=Invalid('synthetic cleanup failure')):
            self.connections.disconnect('sample-one',record['id'],record['version'])
        reloaded=Connections(Store(self.store.path))
        self.assertEqual(reloaded.statuses('sample-one')[record['id']],{'status':'DISCONNECTED','cleanup':'REMOVAL_PENDING'})
        with patch.object(Vault,'get',side_effect=Invalid(self.key)):
            statuses=reloaded.statuses('sample-one')
        self.assertEqual(statuses[record['id']],{'status':'DISCONNECTED','cleanup':'UNCONFIRMED'})
        self.assertNotIn(self.key,json.dumps(statuses))
        current=reloaded.record('sample-one',record['id'])
        reloaded.disconnect('sample-one',record['id'],current['version'])
        self.assertEqual(reloaded.statuses('sample-one')[record['id']],{'status':'DISCONNECTED','cleanup':'NOT_PRESENT'})
        with patch.object(Vault,'get') as read:
            self.assertEqual(reloaded.cleanup_status('sample-one',{}),'NO_PROTECTED_KEY')
            read.assert_not_called()


if __name__=="__main__":
    unittest.main()
