"""Current Windows user secret store; never falls back to plaintext storage."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
from .common import Invalid, canonical, identifier


class Credential(ctypes.Structure):
    _fields_=[("Flags",wintypes.DWORD),("Type",wintypes.DWORD),
              ("TargetName",wintypes.LPWSTR),("Comment",wintypes.LPWSTR),
              ("LastWritten",wintypes.FILETIME),("CredentialBlobSize",wintypes.DWORD),
              ("CredentialBlob",ctypes.POINTER(ctypes.c_ubyte)),("Persist",wintypes.DWORD),
              ("AttributeCount",wintypes.DWORD),("Attributes",ctypes.c_void_p),
              ("TargetAlias",wintypes.LPWSTR),("UserName",wintypes.LPWSTR)]


def namespace(database):
    """Bind local credentials to the database location, not an imported snapshot."""
    return hashlib.sha256(str(Path(database).resolve()).casefold().encode()).hexdigest()[:24]


def target(scope, app_id, provider, reference):
    """Validate every segment before native access; no arbitrary credential names."""
    identifier(app_id)
    if provider not in ("app_store","apple_ads","google_play"):
        raise Invalid("Choose a supported provider")
    if not re.fullmatch(r"[a-f0-9]{24}",str(scope)) or not re.fullmatch(r"[a-f0-9-]{36}",str(reference)):
        raise Invalid("Protected connection reference is invalid; reconnect through setup")
    return f"AppGrowth/{scope}/{app_id}/{provider}/{reference}"


class Vault:
    def __init__(self):
        if os.name!="nt":
            raise Invalid("Protected setup needs Windows Credential Manager on this workstation")
        self.api=ctypes.WinDLL("advapi32",use_last_error=True)
        self.api.CredWriteW.argtypes=[ctypes.POINTER(Credential),wintypes.DWORD]
        self.api.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))]
        self.api.CredDeleteW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD]
        self.api.CredFree.argtypes=[ctypes.c_void_p]
        for name in ("CredWriteW","CredReadW","CredDeleteW"):
            getattr(self.api,name).restype=wintypes.BOOL

    def put(self, name, value):
        """Persist a bounded generic secret for this user on this machine only."""
        raw=canonical(value).encode()
        if len(raw)>2560:
            raise Invalid("Protected credential exceeds the native size limit")
        blob=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
        entry=Credential(Type=1,TargetName=name,CredentialBlobSize=len(raw),CredentialBlob=blob,Persist=2)
        try:
            if not self.api.CredWriteW(ctypes.byref(entry),0):
                raise Invalid("Windows could not protect the credential; prior connection is unchanged")
        finally:
            ctypes.memset(blob,0,len(raw))

    def get(self, name):
        """Read only the exact scoped generic secret and release the native buffer."""
        pointer=ctypes.POINTER(Credential)()
        if not self.api.CredReadW(name,1,0,ctypes.byref(pointer)):
            if ctypes.get_last_error()==1168:
                return None
            raise Invalid("Windows credential store is unavailable; reconnect when unlocked")
        try:
            if pointer.contents.CredentialBlobSize>2560:
                raise Invalid("Protected credential size is invalid")
            return json.loads(ctypes.string_at(pointer.contents.CredentialBlob,pointer.contents.CredentialBlobSize))
        except (ValueError,UnicodeError) as exc:
            raise Invalid("Protected credential is invalid; rotate this connection") from exc
        finally:
            self.api.CredFree(pointer)

    def delete(self, name):
        """Remove the exact local secret; provider key revocation is a separate action."""
        if not self.api.CredDeleteW(name,1,0) and ctypes.get_last_error()!=1168:
            raise Invalid("Windows could not remove this local credential; retry disconnect")
