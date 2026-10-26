"""Real disposable EC signatures and fail-closed optional Linux backend dispatch."""
import base64
import unittest
from unittest.mock import patch
try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec,rsa,utils
    CRYPTO_AVAILABLE=True
except ImportError:
    CRYPTO_AVAILABLE=False
from mission_control.common import Invalid
from mission_control import provider_crypto as crypto,provider_auth as auth


def private_bytes(key):
    return key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())


@unittest.skipUnless(CRYPTO_AVAILABLE,'Optional Linux crypto acceptance dependency is not installed')
class CryptoTests(unittest.TestCase):
    def setUp(self):
        self.key=ec.generate_private_key(ec.SECP256R1());self.raw=private_bytes(self.key)
        self.pem=self.key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()

    def test_execute_inspect_and_sign_exact_p1363_with_no_helpers(self):
        with patch('subprocess.run',side_effect=AssertionError('No helper')),patch('builtins.open',side_effect=AssertionError('No key file')):
            public=crypto.execute('inspect',self.raw)['public_key']
            for message in ('hello','nanna café',''):
                signature=base64.b64decode(crypto.execute('sign',self.raw,message)['signature'],validate=True)
                self.assertEqual(len(signature),64)
                der=utils.encode_dss_signature(int.from_bytes(signature[:32],'big'),int.from_bytes(signature[32:],'big'))
                verifier=serialization.load_pem_public_key(public.encode())
                verifier.verify(der,message.encode(),ec.ECDSA(hashes.SHA256()))
                with self.assertRaises(InvalidSignature):verifier.verify(der,(message+'changed').encode(),ec.ECDSA(hashes.SHA256()))

    def test_execute_rejects_wrong_key_curve_encryption_and_redacts_diagnostics(self):
        wrong=[private_bytes(ec.generate_private_key(ec.SECP384R1())),private_bytes(rsa.generate_private_key(public_exponent=65537,key_size=2048)),
               self.key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo),
               self.key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(b'synthetic-password')),
               b'PRIVATE_INVALID_BYTES',b'',b'x'*2001,None]
        for raw in wrong:
            with self.subTest(kind=type(raw).__name__),self.assertRaises(Invalid) as error:crypto.execute('inspect',raw)
            self.assertNotIn('PRIVATE_INVALID_BYTES',str(error.exception))

    def test_message_bytes_bounds_execute_operations_and_library_dependency_guidance(self):
        for message in (None,'x'*65537,'é'*32769,'\ud800'):
            with self.subTest(kind=type(message).__name__),self.assertRaises(Invalid):crypto.execute('sign',self.raw,message)
        self.assertEqual(len(base64.b64decode(crypto.execute('sign',self.raw,'x'*65536)['signature'])),64)
        with self.assertRaises(Invalid):crypto.execute('unknown',self.raw)
        with patch.object(crypto,'import_module',side_effect=ImportError('private/path')):
            with self.assertRaisesRegex(Invalid,'python3-cryptography') as error:crypto.execute('sign',self.raw,'message')
        self.assertNotIn('private/path',str(error.exception))

    def test_native_platform_dispatch_keeps_windows_cng_and_linux_private_envelope(self):
        with patch.object(auth.sys,'platform','linux'),patch.object(auth,'CNG',side_effect=AssertionError('No Windows API')):
            self.assertIn('PUBLIC KEY',auth.native('inspect',self.pem)['public_key'])
            with self.assertRaises(Invalid):auth.native('inspect',self.pem.replace('PRIVATE KEY','PUBLIC KEY'))
            sec1=self.key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption())
            disguised='-----BEGIN PRIVATE KEY-----\n'+base64.b64encode(sec1).decode()+'\n-----END PRIVATE KEY-----'
            with self.assertRaises(Invalid):auth.native('inspect',disguised)
        with patch.object(auth.sys,'platform','win32'),patch.object(auth,'CNG',side_effect=RuntimeError('Windows CNG selected')):
            with self.assertRaisesRegex(RuntimeError,'Windows CNG selected'):auth.native('inspect',self.pem)
