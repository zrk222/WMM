"""Windows SDK layouts and signatures for ephemeral certificate verification."""
import ctypes as c
from ctypes import wintypes as w

P = c.c_void_p
D = w.DWORD
PP = c.POINTER(P)


class Blob(c.Structure):
    _fields_ = [("size", D), ("data", P)]


class Algorithm(c.Structure):
    _fields_ = [("oid", c.c_char_p), ("parameters", Blob)]


class BitBlob(c.Structure):
    _fields_ = [("size", D), ("data", P), ("unused", D)]


class PublicKey(c.Structure):
    _fields_ = [("algorithm", Algorithm), ("bits", BitBlob)]


class Extension(c.Structure):
    _fields_ = [("oid", c.c_char_p), ("critical", w.BOOL), ("value", Blob)]


class CertInfo(c.Structure):
    _fields_ = [("version", D), ("serial", Blob), ("signature", Algorithm),
                ("issuer", Blob), ("not_before", w.FILETIME), ("not_after", w.FILETIME),
                ("subject", Blob), ("public_key", PublicKey), ("issuer_id", BitBlob),
                ("subject_id", BitBlob), ("extensions_count", D),
                ("extensions", c.POINTER(Extension))]


class Cert(c.Structure):
    _fields_ = [("encoding", D), ("data", P), ("size", D),
                ("info", c.POINTER(CertInfo)), ("store", P)]


class Trust(c.Structure):
    _fields_ = [("error", D), ("info", D)]


class Element(c.Structure):
    _fields_ = [("size", D), ("cert", c.POINTER(Cert)), ("trust", Trust)]


class SimpleChain(c.Structure):
    _fields_ = [("size", D), ("trust", Trust), ("count", D),
                ("elements", c.POINTER(c.POINTER(Element)))]


class Chain(c.Structure):
    _fields_ = [("size", D), ("trust", Trust), ("count", D),
                ("chains", c.POINTER(c.POINTER(SimpleChain)))]


class Usage(c.Structure):
    _fields_ = [("count", D), ("oids", P)]


class UsageMatch(c.Structure):
    _fields_ = [("kind", D), ("usage", Usage)]


class ChainPara(c.Structure):
    _fields_ = [("size", D), ("requested_usage", UsageMatch),
                ("requested_policy", UsageMatch), ("timeout", D),
                ("check_freshness", w.BOOL), ("freshness", D),
                ("resync", c.POINTER(w.FILETIME)), ("strong_sign", P), ("strong_flags", D)]


class EngineConfig(c.Structure):
    _fields_ = [("size", D), ("restricted_root", P), ("restricted_trust", P),
                ("restricted_other", P), ("additional_count", D), ("additional", PP),
                ("flags", D), ("timeout", D), ("cache_max", D), ("cycle_modulus", D),
                ("exclusive_root", P), ("exclusive_people", P), ("exclusive_flags", D)]


def libraries():
    """Load only system cryptographic DLLs with explicit pointer-width signatures."""
    crypt = c.WinDLL("crypt32", use_last_error=True)
    bcrypt = c.WinDLL("bcrypt", use_last_error=True)
    crypt_signatures = {
        "CertOpenStore": ([P, D, P, D, P], P),
        "CertCloseStore": ([P, D], w.BOOL),
        "CertCreateCertificateContext": ([D, P, D], c.POINTER(Cert)),
        "CertFreeCertificateContext": ([c.POINTER(Cert)], w.BOOL),
        "CertAddEncodedCertificateToStore": ([P, D, P, D, D, P], w.BOOL),
        "CertCreateCertificateChainEngine": ([c.POINTER(EngineConfig), PP], w.BOOL),
        "CertFreeCertificateChainEngine": ([P], None),
        "CertGetCertificateChain": ([P, c.POINTER(Cert), c.POINTER(w.FILETIME),
                                    P, c.POINTER(ChainPara), D, P, PP], w.BOOL),
        "CertFreeCertificateChain": ([P], None),
        "CryptImportPublicKeyInfoEx2": ([D, c.POINTER(PublicKey), D, P, PP], w.BOOL),
    }
    bcrypt_signatures = {
        "BCryptExportKey": ([P, P, w.LPCWSTR, P, D, c.POINTER(D), D], c.c_long),
        "BCryptVerifySignature": ([P, P, P, D, P, D, D], c.c_long),
        "BCryptDestroyKey": ([P], c.c_long),
    }
    for library, signatures in ((crypt, crypt_signatures), (bcrypt, bcrypt_signatures)):
        for name, (args, result) in signatures.items():
            function = getattr(library, name)
            function.argtypes = args
            function.restype = result
    return crypt, bcrypt
