"""Ephemeral Windows BCrypt verification of exact named-curve attribution keys."""
import ctypes as c
from ctypes import wintypes as w
import hashlib
import os
import struct
from .common import Invalid

CURVES = {
    "P256": (32, bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d03010703420004"), "nistP256"),
    "P192": (24, bytes.fromhex("3049301306072a8648ce3d020106082a8648ce3d03010103320004"), "nistP192"),
}


def require(condition, message):
    """Use bounded diagnostics that never echo untrusted payloads."""
    if not condition:
        raise Invalid(message)


def public_point(spki, curve):
    """Require exact DER EC algorithm, named curve and uncompressed point."""
    require(isinstance(curve, str) and curve in CURVES, "Attribution curve is unsupported")
    width, prefix, _ = CURVES[curve]
    require(isinstance(spki, bytes) and len(spki) == len(prefix) + 2 * width,
            "Attribution public key length is invalid")
    require(spki.startswith(prefix), "Attribution public key must declare its exact named curve")
    return spki[len(prefix):], width


def signature_integer(raw, offset, width):
    """Decode one positive minimal DER integer without truncation or sign coercion."""
    require(offset + 2 <= len(raw) and raw[offset] == 2, "Attribution DER integer is invalid")
    length = raw[offset + 1]
    start, end = offset + 2, offset + 2 + length
    require(0 < length <= width + 1 and end <= len(raw), "Attribution DER integer width is invalid")
    value = raw[start:end]
    require(value[0] < 128, "Attribution DER integer is negative")
    if value[0] == 0:
        require(len(value) > 1 and value[1] >= 128, "Attribution DER integer is nonminimal or zero")
        value = value[1:]
    require(len(value) <= width and any(value), "Attribution DER integer overflows or is zero")
    return value.rjust(width, b"\x00"), end


def der_signature(raw, curve):
    """Require canonical short DER with exactly two bounded positive integers."""
    require(isinstance(curve, str) and curve in CURVES, "Attribution curve is unsupported")
    width = CURVES[curve][0]
    require(isinstance(raw, bytes) and 6 <= len(raw) <= 2 * width + 8,
            "Attribution DER signature size is invalid")
    require(raw[0] == 48 and raw[1] == len(raw) - 2, "Attribution DER sequence is invalid")
    first, offset = signature_integer(raw, 2, width)
    second, offset = signature_integer(raw, offset, width)
    require(offset == len(raw), "Attribution DER signature contains trailing data")
    return first + second


def libraries():
    """Load the Windows system DLL with explicit pointer-width ABI declarations."""
    require(os.name == "nt", "Native attribution verification requires Windows")
    dll = c.WinDLL("bcrypt.dll", winmode=0x800)
    pointer, size = c.c_void_p, w.ULONG
    signatures = {
        "BCryptOpenAlgorithmProvider": ([c.POINTER(pointer), w.LPCWSTR, w.LPCWSTR, size], c.c_long),
        "BCryptSetProperty": ([pointer, w.LPCWSTR, pointer, size, size], c.c_long),
        "BCryptImportKeyPair": ([pointer, pointer, w.LPCWSTR, c.POINTER(pointer), pointer, size, size], c.c_long),
        "BCryptVerifySignature": ([pointer, pointer, pointer, size, pointer, size, size], c.c_long),
        "BCryptDestroyKey": ([pointer], c.c_long),
        "BCryptCloseAlgorithmProvider": ([pointer, size], c.c_long),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = arguments, result
    return dll


def open_curve(dll, handle, curve):
    """Require the named curve, including legacy P192, instead of guessing by width."""
    require(dll.BCryptOpenAlgorithmProvider(c.byref(handle), "ECDSA", None, 0) == 0,
            "Windows attribution ECDSA provider is unavailable")
    name = c.create_unicode_buffer(CURVES[curve][2])
    require(dll.BCryptSetProperty(handle, "ECCCurveName", name, c.sizeof(name), 0) == 0,
            "Windows attribution named curve is unavailable")


def verify(spki,curve,message,signature):
    """Verify SHA256/P1363 with transient handles; never persist keys or alter trust."""
    point, width = public_point(spki, curve)
    require(isinstance(message, bytes) and 0 < len(message) <= 262144,
            "Attribution signed message size is invalid")
    require(isinstance(signature, bytes) and len(signature) == 2 * width,
            "Attribution raw signature size is invalid")
    require(any(signature[:width]) and any(signature[width:]), "Attribution signature has a zero integer")
    dll = libraries()
    algorithm, key = c.c_void_p(), c.c_void_p()
    try:
        open_curve(dll, algorithm, curve)
        blob = c.create_string_buffer(struct.pack("<II", 0x50444345, width) + point)
        require(dll.BCryptImportKeyPair(algorithm, None, "ECCPUBLICBLOB", c.byref(key),
                                       blob, 8 + 2 * width, 0) == 0,
                "Attribution public key import failed")
        hashed = c.create_string_buffer(hashlib.sha256(message).digest())
        signed = c.create_string_buffer(signature)
        require(dll.BCryptVerifySignature(key, None, hashed, 32, signed, len(signature), 0) == 0,
                "Attribution signature verification failed")
    finally:
        if key.value:
            dll.BCryptDestroyKey(key)
        if algorithm.value:
            dll.BCryptCloseAlgorithmProvider(algorithm, 0)
