"""Optional Linux Apple ES256 signing through validated in-memory library keys."""
import base64
from importlib import import_module
from .common import Invalid


def library():
    """Load explicitly installed crypto support only when this platform requests it."""
    try:
        return (import_module('cryptography.hazmat.primitives.serialization'),
                import_module('cryptography.hazmat.primitives.asymmetric.ec'),
                import_module('cryptography.hazmat.primitives.asymmetric.utils'),
                import_module('cryptography.hazmat.primitives.hashes'),
                import_module('cryptography.exceptions').UnsupportedAlgorithm)
    except ImportError:
        raise Invalid('Linux Apple API signing needs python3-cryptography in the selected Python environment; install the documented package and retry.') from None


def message_bytes(message):
    """Bound exact UTF-8 bytes before invoking any signing backend."""
    if not isinstance(message,str) or len(message)>65536:raise Invalid('Signing message exceeds the permitted size')
    try:payload=message.encode('utf-8')
    except UnicodeError:raise Invalid('Signing message encoding is invalid') from None
    if len(payload)>65536:raise Invalid('Signing message exceeds the permitted size')
    return payload


def execute(operation,raw,message=''):
    """Inspect one validated P-256 key or return one exact 64-byte P1363 signature."""
    if operation not in ('inspect','sign'):raise Invalid('Unknown native key operation')
    if not isinstance(raw,bytes) or not 1<=len(raw)<=2000:raise Invalid('Private key must be bounded PKCS8 P-256')
    payload=message_bytes(message)
    serialization,ec,utils,hashes,unsupported=library()
    try:
        key=serialization.load_der_private_key(raw,password=None)
        if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):
            raise Invalid('Key must use ECDSA P-256')
        if operation=='inspect':
            public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
            return dict(public_key=public.decode('ascii').strip())
        r,s=utils.decode_dss_signature(key.sign(payload,ec.ECDSA(hashes.SHA256())))
        signature=r.to_bytes(32,'big')+s.to_bytes(32,'big')
        return dict(signature=base64.b64encode(signature).decode('ascii'))
    except (ValueError,TypeError,OverflowError,unsupported):
        raise Invalid('Key validation or signing failed; verify the authorized PKCS8 P-256 key') from None
