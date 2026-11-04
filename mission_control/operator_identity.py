"""Ephemeral GitHub-authenticated operator sessions; no stored or exported tokens."""
import json
import re
import secrets
import ssl
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener
from .common import Invalid, now
from .providers import NoRedirect


def _identity_trust_context():
    """Use native Windows certificate verification without global SSL changes."""
    if sys.platform == "win32":
        try:
            import truststore
        except ImportError as exc:
            raise Invalid("Windows identity verification requires the bundled native trust provider") from exc
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    else:
        context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def _github_opener(context=None):
    """Build a fixed GitHub reader for one verified trust profile."""
    if context is None:
        context = _identity_trust_context()
    return build_opener(NoRedirect(), HTTPSHandler(context=context))


def github_read(path,token):
    """Read only fixed identity endpoints with bounded bytes and no redirects."""
    if not re.fullmatch(r"/user|/users/[A-Za-z0-9-]{1,39}",path):raise Invalid("Unapproved identity endpoint")
    headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,
             "X-GitHub-Api-Version":"2026-03-10","User-Agent":"App-Growth-Mission-Control"}
    # Native verification failures never retry through a different trust engine.
    # urllib's 15-second timeout applies per blocking I/O, not to the whole response.
    opener=_github_opener()
    request=Request("https://api.github.com"+path,headers=headers,method="GET")
    try:
        with opener.open(request,timeout=15) as response:
            raw=response.read(65537)
    except HTTPError as exc:raise Invalid(f"GitHub identity verification returned HTTP {exc.code}; sign in again or check access") from exc
    except (URLError,ssl.SSLError,TimeoutError) as exc:
        raise Invalid("GitHub identity verification is unavailable; saved work is preserved") from exc
    if len(raw)>65536:raise Invalid("GitHub identity response exceeds the supported size")
    try:return identity(json.loads(raw))
    except (ValueError,TypeError,AttributeError) as exc:raise Invalid("GitHub identity response is invalid") from exc


def identity(data):
    """Use durable numeric human-account identity, never a supplied display name."""
    if not isinstance(data,dict) or data.get("type")!="User" or type(data.get("id")) is not int or data["id"]<=0:
        raise Invalid("A verified individual GitHub account is required")
    login=data.get("login")
    if not isinstance(login,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}",login):raise Invalid("GitHub returned an invalid user login")
    return {"principal":"github:"+str(data["id"]),"login":login,"provider":"GITHUB","verified_at":now()}


class Identities:
    def __init__(self):
        self.sessions={}
        self.lock=threading.RLock()

    def login(self,session,body):
        """Authenticate once and retain only a bounded in-memory session credential."""
        token=body.get("token")
        if set(body)!={"token"} or not isinstance(token,str) or not re.fullmatch(r"[A-Za-z0-9_]{20,256}",token):
            raise Invalid("Enter a GitHub personal access token; no repository permissions are needed")
        user=github_read("/user",token)
        with self.lock:
            self.prune()
            self.sessions[session]={"token":token,"user":user,"expires":time.time()+900}
        return self.public(session)

    def prune(self):
        """Remove expired credentials from RAM rather than retaining dead sessions."""
        for key,row in list(self.sessions.items()):
            if row["expires"]<=time.time():self.sessions.pop(key,None)

    def public(self,session):
        """Return public authenticated identity metadata without its bearer token."""
        with self.lock:
            self.prune();row=self.sessions.get(session)
            if not row:return {"status":"SIGNED_OUT"}
            return {"status":"AUTHENTICATED",**row["user"],"expires_at_epoch":row["expires"]}

    def logout(self,session):
        """Discard the credential immediately; provider token revocation is separate."""
        with self.lock:self.sessions.pop(session,None)
        return {"status":"SIGNED_OUT"}

    def fresh(self,session):
        """Revalidate the actual credential for every protected action, failing closed."""
        with self.lock:
            self.prune();row=self.sessions.get(session)
            if not row:raise PermissionError("Sign in with GitHub before changing verified access or reviews")
            try:user=github_read("/user",row["token"])
            except Exception:
                self.sessions.pop(session,None)
                raise
            if user["principal"]!=row["user"]["principal"]:
                self.sessions.pop(session,None)
                raise PermissionError("Authenticated identity changed; sign in again")
            row["user"]=user
            return dict(user)

    def local(self,session,principal,generation=None):
        """Recheck admitted local identity without provider I/O during native work."""
        with self.lock:
            self.prune();row=self.sessions.get(session)
            if not row or row['user']['principal']!=principal:
                raise PermissionError('Authenticated operator session changed; sign in again')
            current=row.setdefault('generation',secrets.token_hex(16))
            if generation is not None and generation!=current:
                raise PermissionError('Authenticated operator session was replaced; sign in again')
            return dict(row['user'],session_generation=current)

    def lookup(self,session,login):
        """Resolve a human member's immutable ID, using only the current own session."""
        if not isinstance(login,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}",login):raise Invalid("Enter the member's GitHub username")
        with self.lock:
            self.prune();row=self.sessions.get(session)
            if not row:raise PermissionError("Sign in before looking up a reviewer")
            return github_read("/users/"+login,row["token"])
