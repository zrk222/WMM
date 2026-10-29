"""Native Apple signing and app-bound protected Apple/Google credential renewal."""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import re
import struct
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener
from .common import Invalid, canonical
from .credential_vault import Vault, target

LOCK=threading.RLock()
CACHE={}
NATIVE_CONTEXT=ContextVar('wmm_store_native_context',default=None)
NATIVE_PAGE_GUARD=ContextVar('wmm_store_native_page_guard',default=None)


@contextmanager
def bound_page_guard(check):
    if NATIVE_CONTEXT.get() is None or not callable(check):raise PermissionError('Native page guard requires a trusted host')
    token=NATIVE_PAGE_GUARD.set(check)
    try:yield
    finally:NATIVE_PAGE_GUARD.reset(token)


def check_native_page():
    if NATIVE_CONTEXT.get() is not None:
        guard=NATIVE_PAGE_GUARD.get()
        if guard is None:raise PermissionError('Native provider read requires an owner and job guard')
        guard()


@contextmanager
def bound_native(scope,app_id,vault_factory,signer):
    """Bind native-only storage and signing to one database/app for this call."""
    if not callable(vault_factory) or not callable(signer):raise Invalid('Native protected storage and signer are required')
    context=NATIVE_CONTEXT.set((scope,app_id,vault_factory,signer))
    try:yield
    finally:NATIVE_CONTEXT.reset(context)


def vault_for(scope,app_id):
    context=NATIVE_CONTEXT.get()
    if context is None:return Vault()
    if context[:2]!=(scope,app_id):raise PermissionError('Native credential scope changed')
    return context[2]()


def key_der(private_key):
    """Decode only bounded unencrypted PKCS8 private PEM; native parser validates ASN.1."""
    if not isinstance(private_key,str) or len(private_key)>2000:
        raise Invalid("Upload a bounded unencrypted P-256 private key")
    match=re.fullmatch(r"\s*-----BEGIN PRIVATE KEY-----\s+([A-Za-z0-9+/=\s]+)\s+-----END PRIVATE KEY-----\s*",private_key)
    if not match:
        raise Invalid("Upload a PKCS8 P-256 private key (.p8 or PEM with BEGIN PRIVATE KEY)")
    try:
        return base64.b64decode(re.sub(r"\s","",match[1]),validate=True)
    except ValueError as exc:
        raise Invalid("Private key file encoding is invalid") from exc


def der_values(data):
    """Decode bounded definite-length DER containers without interpreting algorithms."""
    values=[]
    offset=0
    while offset<len(data):
        if offset+2>len(data):raise Invalid("Private DER key is truncated")
        tag,size=data[offset:offset+2];offset+=2
        if size&128:
            count=size&127
            if not 1<=count<=2 or offset+count>len(data):raise Invalid("Private DER length is invalid")
            size=int.from_bytes(data[offset:offset+count],"big");offset+=count
        if offset+size>len(data):raise Invalid("Private DER key is truncated")
        values.append((tag,data[offset:offset+size]));offset+=size
    return values


def private_scalar(raw):
    """Extract exactly the 32-byte EC scalar after native PKCS8 validation."""
    outer=der_values(raw)
    if len(outer)!=1 or outer[0][0]!=48:raise Invalid("Private key must be PKCS8")
    pkcs8=der_values(outer[0][1])
    if len(pkcs8)<3 or pkcs8[2][0]!=4:raise Invalid("Private key must be PKCS8")
    ec=der_values(pkcs8[2][1])
    if len(ec)!=1 or ec[0][0]!=48:raise Invalid("Private key must contain an EC key")
    values=der_values(ec[0][1])
    if len(values)<2 or values[1][0]!=4 or len(values[1][1])!=32:
        raise Invalid("Private key must use P-256")
    return values[1][1]


def sign_p256(public,scalar,message):
    """Import a validated P-256 pair as ECDSA and sign with native BCrypt."""
    api=ctypes.WinDLL("bcrypt")
    h=ctypes.c_void_p;ptr=ctypes.c_void_p;n=wintypes.DWORD
    signatures={"BCryptOpenAlgorithmProvider":[ctypes.POINTER(h),wintypes.LPCWSTR,wintypes.LPCWSTR,n],
                "BCryptImportKeyPair":[h,h,wintypes.LPCWSTR,ctypes.POINTER(h),ptr,n,n],
                "BCryptSignHash":[h,ptr,ptr,n,ptr,n,ctypes.POINTER(n),n],
                "BCryptDestroyKey":[h],"BCryptCloseAlgorithmProvider":[h,n]}
    for name,args in signatures.items():
        getattr(api,name).argtypes=args;getattr(api,name).restype=ctypes.c_long
    algorithm=h();key=h();buffer=ctypes.create_string_buffer(struct.pack("<II",0x32534345,32)+public+scalar)
    try:
        check_status(api.BCryptOpenAlgorithmProvider(ctypes.byref(algorithm),"ECDSA_P256",None,0))
        check_status(api.BCryptImportKeyPair(algorithm,None,"ECCPRIVATEBLOB",ctypes.byref(key),buffer,104,0))
        digest=ctypes.create_string_buffer(hashlib.sha256(message.encode()).digest())
        output=ctypes.create_string_buffer(64);length=n()
        check_status(api.BCryptSignHash(key,None,digest,32,output,64,ctypes.byref(length),0))
        if length.value!=64:raise Invalid("Native ES256 signature length is invalid")
        return base64.b64encode(output.raw).decode()
    finally:
        ctypes.memset(buffer,0,104)
        if key.value:api.BCryptDestroyKey(key)
        if algorithm.value:api.BCryptCloseAlgorithmProvider(algorithm,0)


def check_status(status):
    """Convert native errors to redacted user guidance."""
    if status:raise Invalid("Native key validation or signing failed; verify the authorized P-256 key")


class CNG:
    def __init__(self):
        self.api=ctypes.WinDLL("ncrypt")
        handle=ctypes.c_size_t
        pointer=ctypes.c_void_p
        number=wintypes.DWORD
        signatures={
            "NCryptOpenStorageProvider":[ctypes.POINTER(handle),wintypes.LPCWSTR,number],
            "NCryptImportKey":[handle,handle,wintypes.LPCWSTR,pointer,ctypes.POINTER(handle),pointer,number,number],
            "NCryptExportKey":[handle,handle,wintypes.LPCWSTR,pointer,pointer,number,ctypes.POINTER(number),number],
            "NCryptFreeObject":[handle],
        }
        for name,args in signatures.items():
            function=getattr(self.api,name);function.argtypes=args;function.restype=ctypes.c_long

    def check(self,status):
        """Never disclose native input or full diagnostics in a public error."""
        if status:
            raise Invalid("Native key validation or signing failed; verify the authorized P-256 key")

    def import_key(self,provider,raw):
        """Import an unnamed ephemeral PKCS8 key and erase the native input buffer."""
        key=ctypes.c_size_t()
        buffer=ctypes.create_string_buffer(raw)
        try:
            self.check(self.api.NCryptImportKey(provider,0,"PKCS8_PRIVATEKEY",None,ctypes.byref(key),buffer,len(raw),0x40))
        finally:
            ctypes.memset(buffer,0,len(raw))
        return key

    def public_key(self,key):
        """Require exact ECDSA P-256 magic/size before converting public coordinates to PEM."""
        output=ctypes.create_string_buffer(72)
        length=wintypes.DWORD()
        self.check(self.api.NCryptExportKey(key,0,"ECCPUBLICBLOB",None,output,72,ctypes.byref(length),0))
        if length.value!=72 or struct.unpack("<II",output.raw[:8]) not in ((0x31534345,32),(0x314b4345,32)):
            raise Invalid("Key must use ECDSA P-256")
        self.coordinates=output.raw[8:72]
        prefix=bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d03010703420004")
        encoded=base64.b64encode(prefix+output.raw[8:72]).decode()
        return "-----BEGIN PUBLIC KEY-----\n"+"\n".join(encoded[i:i+64] for i in range(0,len(encoded),64))+"\n-----END PUBLIC KEY-----"

def native(operation,private_key,message=""):
    """Select local platform signing without a helper or persistent private-key file."""
    raw=key_der(private_key)
    context=NATIVE_CONTEXT.get()
    if context is not None:
        from .ios_bridge import decode_document
        response=decode_document(context[3](canonical(dict(operation=operation,private_key=private_key,message=message)).encode()))
        if not isinstance(response,dict) or set(response)!={'ok','value'} or response['ok'] is not True or not isinstance(response['value'],dict):
            raise Invalid('Native Apple signing is unavailable')
        value=response['value']
        if (operation=='inspect' and set(value)=={'public_key'} and isinstance(value['public_key'],str)
                and len(value['public_key'])<=1024
                and re.fullmatch(r'-----BEGIN PUBLIC KEY-----[\s\S]+-----END PUBLIC KEY-----\s*',value['public_key'])):return value
        if operation=='sign' and set(value)=={'signature'} and isinstance(value['signature'],str):
            try:
                if len(base64.b64decode(value['signature'],validate=True))==64:return value
            except (ValueError,TypeError):pass
        raise Invalid('Native Apple signing response is invalid')
    if sys.platform.startswith('linux'):
        from .provider_crypto import execute
        private_scalar(raw)
        return execute(operation,raw,message)
    provider=ctypes.c_size_t()
    key=ctypes.c_size_t()
    api=CNG()
    try:
        api.check(api.api.NCryptOpenStorageProvider(ctypes.byref(provider),"Microsoft Software Key Storage Provider",0))
        key=api.import_key(provider,raw)
        public=api.public_key(key)
        if operation=="inspect":
            return {"public_key":public}
        if operation=="sign":
            return {"signature":sign_p256(api.coordinates,private_scalar(raw),message)}
        raise Invalid("Unknown native key operation")
    finally:
        if key.value:api.api.NCryptFreeObject(key)
        if provider.value:api.api.NCryptFreeObject(provider)


def encoded(value):
    """Encode canonical JWT parts without padding."""
    return base64.urlsafe_b64encode(canonical(value).encode()).decode().rstrip("=")


def jwt(config, clock):
    """Issue short-lived documented team-key tokens with P1363 ES256 signatures."""
    header={"alg":"ES256","kid":config["key_id"],"typ":"JWT"}
    claims={"iss":config["issuer_id"],"iat":clock,"exp":clock+600,"aud":"appstoreconnect-v1"}
    if config["provider"]=="apple_ads":
        claims.update(sub=config["client_id"],aud="https://appleid.apple.com",exp=clock+3600)
    message=encoded(header)+"."+encoded(claims)
    signature=base64.b64decode(native("sign",config["private_key"],message)["signature"],validate=True)
    if len(signature)!=64:
        raise Invalid("Native signer did not produce a valid ES256 signature")
    return message+"."+base64.urlsafe_b64encode(signature).decode().rstrip("=")


class BlockRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        """Never forward token credentials through a redirect."""
        raise Invalid("Apple token redirect blocked; no credentials forwarded")


def exchange(config, client_secret):
    """Exchange only at the documented fixed Apple authorization endpoint."""
    body=urlencode({"grant_type":"client_credentials","client_id":config["client_id"],"client_secret":client_secret,"scope":"searchadsorg"}).encode()
    request=Request("https://appleid.apple.com/auth/oauth2/token",data=body,headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"},method="POST")
    try:
        with build_opener(BlockRedirect()).open(request,timeout=15) as response:
            raw=response.read(16385)
        if len(raw)>16384:
            raise Invalid("Apple token response exceeds the permitted limit")
        payload=json.loads(raw)
    except HTTPError as exc:
        raise Invalid(f"Apple token HTTP {exc.code}; verify registered public key, IDs and API role") from exc
    except (URLError,TimeoutError,ValueError,UnicodeError) as exc:
        raise Invalid("Apple token exchange failed; saved connection is preserved, retry later") from exc
    return token_response(payload)


def token_response(payload):
    """Reject undocumented token type, scope, lifetime or malformed bearer."""
    if not isinstance(payload,dict) or payload.get("token_type")!="Bearer" or payload.get("scope")!="searchadsorg":
        raise Invalid("Apple returned an invalid token scope or type")
    token=payload.get("access_token")
    lifetime=payload.get("expires_in")
    if not isinstance(token,str) or not 1<=len(token)<=8192 or any(c.isspace() for c in token):
        raise Invalid("Apple returned an invalid access token")
    if type(lifetime) is not int or not 120<=lifetime<=3600:
        raise Invalid("Apple returned an invalid token lifetime")
    return token,lifetime


def credential(binding, app_id):
    """Resolve namespace-bound secret and renew before expiry without persisting tokens."""
    name=target(binding.get("_vault_namespace"),app_id,binding.get("provider"),binding.get("credential_ref"))
    with LOCK:
        config=vault_for(binding.get('_vault_namespace'),app_id).get(name)
        if not config:
            CACHE.pop(name,None)
            raise Invalid("Protected key is missing for this database; reconnect through provider setup")
        clock=int(time.time())
        if binding.get('provider')=='google_play':
            return google_credential(binding,app_id,name,config,clock)
        cached=None if NATIVE_CONTEXT.get() is not None else CACHE.get(name)
        if cached and cached[1]>clock+60:
            return cached[0]
        token=jwt(config,clock)
        lifetime=600
        if binding["provider"]=="apple_ads":
            token,lifetime=exchange(config,token)
        if NATIVE_CONTEXT.get() is None:CACHE[name]=(token,clock+lifetime)
        return token


def google_credential(binding,app_id,name,config,clock):
    """Validate protected app/target scope before reusing or renewing a Google bearer."""
    from .play_contract import connection_metadata, SCOPE
    from .play_auth import refresh
    selected=connection_metadata(binding)
    expected=dict(app_id=app_id,**selected,client_id=binding['client_id'])
    if config.get('binding')!=expected or config.get('scopes')!=[SCOPE] or binding.get('auth_mode')!='managed_oauth':
        raise Invalid('Protected Google grant does not match this app target; reconnect')
    cached=CACHE.get(name)
    if cached and cached[1]>clock+60:return cached[0]
    grant=refresh(config)
    if grant['refresh_token']!=config['refresh_token']:
        Vault().put(name,dict(config,refresh_token=grant['refresh_token']))
    CACHE[name]=(grant['access_token'],clock+grant['expires_in'])
    return grant['access_token']


def forget(name):
    """Remove in-process token after rotation or local disconnect."""
    with LOCK:
        CACHE.pop(name,None)
