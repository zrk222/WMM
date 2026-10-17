"""Fail-closed ephemeral Crypt32 chain verification and BCrypt ES256 verification."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import os
import struct
import time
from .common import Invalid
from . import storekit_abi as abi
from .storekit_trust import pinned_roots

LEAF_OID = b"1.2.840.113635.100.6.11.1"
INTERMEDIATE_OID = b"1.2.840.113635.100.6.2.1"
OFFLINE_FLAGS = 4 | 8192 | 256
ONLINE_FLAGS = 8192 | 256 | 1073741824 | 134217728


def require(condition, message):
    """Keep untrusted certificate contents out of diagnostics."""
    if not condition:
        raise Invalid(message)


def filetime(stamp):
    """Convert a Unix clock to the native UTC FILETIME ABI."""
    ticks = int((stamp + 11644473600) * 10000000)
    return w.FILETIME(ticks & 0xffffffff, ticks >> 32)


def has_oid(cert, wanted):
    """Inspect only a bounded native-parsed extension array."""
    info = cert.contents.info.contents
    require(info.extensions_count <= 64, "Certificate extension count exceeds limit")
    return any(info.extensions[i].oid == wanted for i in range(info.extensions_count))


def cert_bytes(cert):
    """Read native-parsed DER only after enforcing the input cap again."""
    require(0 < cert.contents.size <= 8192, "Certificate size is invalid")
    return c.string_at(cert.contents.data, cert.contents.size)


def check_chain(pointer, expected):
    """Reject alternate cached paths, extra chains and every native trust error."""
    chain = c.cast(pointer, c.POINTER(abi.Chain)).contents
    require(chain.trust.error == 0, "Certificate trust or revocation failed; retry with network available")
    require(chain.count == 1, "Certificate chain count is invalid")
    simple = chain.chains[0].contents
    require(simple.trust.error == 0 and simple.count == 3, "Certificate chain is invalid")
    actual = [cert_bytes(simple.elements[i].contents.cert) for i in range(simple.count)]
    require(actual == list(expected), "Certificate chain does not match the supplied pinned path")
    require(all(simple.elements[i].contents.trust.error == 0 for i in range(simple.count)),
            "Certificate element trust failed")


class NativeVerifier:
    """Internal explicit-root engine. Production uses verify_apple only."""

    def __init__(self, roots):
        require(os.name == "nt", "StoreKit verification requires Windows native cryptography")
        require(1 <= len(roots) <= 3, "Pinned root count is invalid")
        require(all(isinstance(raw, bytes) and 0 < len(raw) <= 8192 for raw in roots),
                "Pinned root size is invalid")
        self.roots = tuple(roots)
        self.crypt, self.bcrypt = abi.libraries()
        self.root_store = None
        self.other_store = None
        self.engine = abi.P()
        self.certs = []

    def add(self, store, raw):
        """Memory-store addition makes a native copy, never changes system trust."""
        buffer = c.create_string_buffer(raw)
        require(self.crypt.CertAddEncodedCertificateToStore(store, 1, buffer, len(raw), 4, None),
                "Certificate memory-store parsing failed")

    def prepare(self, certs):
        """Require a pinned supplied root before constructing an exclusive engine."""
        require(len(certs) == 3 and all(isinstance(raw, bytes) and 0 < len(raw) <= 8192 for raw in certs),
                "Certificate chain input is invalid")
        require(certs[2] in self.roots, "Certificate root is not pinned")
        self.root_store = self.crypt.CertOpenStore(abi.P(2), 0, None, 0, None)
        self.other_store = self.crypt.CertOpenStore(abi.P(2), 0, None, 0, None)
        require(self.root_store and self.other_store, "Certificate memory store is unavailable")
        for raw in self.roots:
            self.add(self.root_store, raw)
        for raw in certs[:2]:
            self.add(self.other_store, raw)
            buffer = c.create_string_buffer(raw)
            cert = self.crypt.CertCreateCertificateContext(1, buffer, len(raw))
            require(bool(cert), "Certificate parsing failed")
            self.certs.append(cert)
        require(has_oid(self.certs[0], LEAF_OID), "Apple signing certificate extension is missing")
        require(has_oid(self.certs[1], INTERMEDIATE_OID), "Apple intermediate certificate extension is missing")
        config = abi.EngineConfig()
        config.size = c.sizeof(config)
        config.exclusive_root = self.root_store
        config.flags = 8192
        config.timeout = 5000
        require(self.crypt.CertCreateCertificateChainEngine(c.byref(config), c.byref(self.engine)),
                "Exclusive certificate engine is unavailable")

    def chain(self, certs, online, now):
        """Validate current time, and optionally require fresh native revocation."""
        params = abi.ChainPara()
        params.size = c.sizeof(params)
        params.timeout = 5000
        params.check_freshness = bool(online)
        params.freshness = 300
        resync = filetime(now - 300)
        params.resync = c.pointer(resync)
        current = filetime(now)
        result = abi.P()
        flags = ONLINE_FLAGS if online else OFFLINE_FLAGS
        try:
            require(self.crypt.CertGetCertificateChain(self.engine, self.certs[0], c.byref(current),
                    self.other_store, c.byref(params), flags, None, c.byref(result)),
                    "Certificate trust or revocation service is unavailable; retry")
            require(bool(result.value), "Native certificate chain returned no context")
            check_chain(result, certs)
        finally:
            if result.value:
                self.crypt.CertFreeCertificateChain(result)

    def signature(self, message, signature):
        """Use the leaf public key to verify a P1363 ES256 signature, with cleanup."""
        require(isinstance(message, bytes) and isinstance(signature, bytes) and len(signature) == 64,
                "ES256 signature input is invalid")
        key = abi.P()
        try:
            public = self.certs[0].contents.info.contents.public_key
            require(self.crypt.CryptImportPublicKeyInfoEx2(1, c.byref(public), 0, None, c.byref(key)),
                    "Native certificate public key is invalid")
            self.require_p256(key)
            digest = c.create_string_buffer(hashlib.sha256(message).digest())
            signed = c.create_string_buffer(signature)
            require(self.bcrypt.BCryptVerifySignature(key, None, digest, 32, signed, 64, 0) == 0,
                    "StoreKit ES256 signature is invalid")
        finally:
            if key.value:
                self.bcrypt.BCryptDestroyKey(key)

    def require_p256(self, key):
        """Reject another curve even when its native signature primitive is usable."""
        blob = c.create_string_buffer(72)
        length = abi.D()
        require(self.bcrypt.BCryptExportKey(key, None, "ECCPUBLICBLOB", blob, 72, c.byref(length), 0) == 0,
                "Certificate must use a P256 public key")
        require(length.value == 72 and struct.unpack("<II", blob.raw[:8]) in
                ((0x31534345, 32), (0x314b4345, 32)), "Certificate must use a P256 public key")

    def close(self):
        """Release partial constructions too; no native trust handles escape."""
        if self.engine.value:
            self.crypt.CertFreeCertificateChainEngine(self.engine)
            self.engine = abi.P()
        for cert in self.certs:
            self.crypt.CertFreeCertificateContext(cert)
        self.certs = []
        for store in (self.other_store, self.root_store):
            if store:
                self.crypt.CertCloseStore(store, 0)
        self.other_store = self.root_store = None

    def verify(self, certs, message, signature, online=True, clock=None):
        """Anchor trust offline before permitting certificate network retrieval."""
        try:
            self.prepare(certs)
            now = time.time() if clock is None else clock
            self.chain(certs, False, now)
            self.signature(message, signature)
            if online:
                self.chain(certs, True, now)
        finally:
            self.close()


def verify_apple(certs, message, signature):
    """The sole production boundary always pins official roots and checks revocation."""
    NativeVerifier(pinned_roots()).verify(certs, message, signature, online=True)
