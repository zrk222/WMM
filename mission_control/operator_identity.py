"""Ephemeral GitHub-authenticated operator sessions; no stored or exported tokens."""
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from .common import Invalid, now
from .providers import NoRedirect


def github_read(path,token):
    """Read only fixed identity endpoints with bounded bytes and no redirects."""
    if not re.fullmatch(r"/user|/users/[A-Za-z0-9-]{1,39}",path):raise Invalid("Unapproved identity endpoint")
    headers={"Accept":"application/vnd.github+json","Authorization":"Bearer "+token,
             "X-GitHub-Api-Version":"2026-03-10","User-Agent":"App-Growth-Mission-Control"}
    try:
        with build_opener(NoRedirect()).open(Request("https://api.github.com"+path,headers=headers,method="GET"),timeout=15) as response:
            raw=response.read(65537)
    except HTTPError as exc:raise Invalid(f"GitHub identity verification returned HTTP {exc.code}; sign in again or check access") from exc
    except (URLError,TimeoutError) as exc:raise Invalid("GitHub identity verification is unavailable; saved work is preserved") from exc
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

    def lookup(self,session,login):
        """Resolve a human member's immutable ID, using only the current own session."""
        if not isinstance(login,str) or not re.fullmatch(r"[A-Za-z0-9-]{1,39}",login):raise Invalid("Enter the member's GitHub username")
        with self.lock:
            self.prune();row=self.sessions.get(session)
            if not row:raise PermissionError("Sign in before looking up a reviewer")
            return github_read("/users/"+login,row["token"])
