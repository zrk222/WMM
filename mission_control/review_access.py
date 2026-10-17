"""Trusted-workstation bootstrap and version-bound, app-specific authenticated roles."""
import json
from .common import Invalid, canonical, now
from .db import connection
from .store import audit


def member(db,app_id,principal,role=None):
    """Require the current active membership and exact app-scoped capability."""
    row=db.execute("SELECT * FROM operator_roles WHERE app_id=? AND principal=?",(app_id,principal)).fetchone()
    if not row or row["status"]!="ACTIVE":raise PermissionError("This GitHub account has no active role in this app")
    if role and row["role"] not in (role,"OWNER"):raise PermissionError("This action requires the app's "+role.lower()+" role")
    return dict(row)


def exact_role(db,app_id,principal,version,role):
    """Prevent revoke/reactivate or role changes from resurrecting an old approval."""
    row=member(db,app_id,principal,role)
    if row["version"]!=version:raise Invalid("The app role changed; prepare a new review")
    return row


def member_body(body):
    """Validate finite membership fields separately from transactional authorization."""
    if set(body)!={"login","role","status","version"} or body["role"] not in ("MAKER","CHECKER") or body["status"] not in ("ACTIVE","REVOKED"):
        raise Invalid("Choose a maker or checker role and active or revoked status")
    if body["version"] is not None and (type(body["version"]) is not int or body["version"]<1):raise Invalid("Use the exact current member version")


class Access:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Expose local access policy and history without impersonation or secrets."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM operator_roles WHERE app_id=? ORDER BY principal",(app_id,))]
        return {"configured":bool(rows),"members":rows,"bootstrap":"First verified owner on this trusted local workstation",
                "identity_provider":"GITHUB","external_execution":"NOT_IMPLEMENTED","snapshot_authority":"NOT_EXPORTED"}

    def bootstrap(self,app_id,user,body):
        """Establish exactly one verified owner on an unconfigured local workspace."""
        self.store.app(app_id)
        if body!={"confirm_owner":True}:raise Invalid("Confirm that you are establishing the first owner for this local app")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM operator_roles WHERE app_id=?",(app_id,)).fetchone():raise Invalid("This app already has an owner; ask that owner to assign your role")
            self.write(db,app_id,user,"OWNER","ACTIVE",1,user["principal"])
            audit(db,app_id,"access.owner_established",{"principal":user["principal"],"policy":"TRUSTED_LOCAL_BOOTSTRAP"})
        return self.list(app_id)

    def save(self,app_id,owner,user,body):
        """Update only maker/checker membership under current authenticated owner."""
        self.store.app(app_id)
        member_body(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app_id,owner["principal"],"OWNER")
            old=db.execute("SELECT * FROM operator_roles WHERE app_id=? AND principal=?",(app_id,user["principal"])).fetchone()
            if old and old["role"]=="OWNER":raise Invalid("The established app owner cannot be replaced through member setup")
            expected=old["version"] if old else None
            if body["version"]!=expected:raise Invalid("Member access changed; reload before saving")
            version=(expected or 0)+1
            self.write(db,app_id,user,body["role"],body["status"],version,owner["principal"])
            audit(db,app_id,"access.member_changed",{"principal":user["principal"],"role":body["role"],"status":body["status"],"version":version,"owner":owner["principal"]})
        return self.list(app_id)

    def write(self,db,app_id,user,role,status,version,owner):
        """Persist public immutable principal binding and audited current role version."""
        db.execute("INSERT INTO operator_roles(app_id,principal,login,role,status,version,updated,changed_by) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(app_id,principal) DO UPDATE SET login=excluded.login,role=excluded.role,status=excluded.status,version=excluded.version,updated=excluded.updated,changed_by=excluded.changed_by",
                   (app_id,user["principal"],user["login"],role,status,version,now(),owner))
