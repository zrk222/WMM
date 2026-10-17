"""Protected setup transaction; records carry only public metadata and references."""
import re
from .common import Invalid, required, uid
from .credential_vault import Vault, namespace, target
from .provider_auth import LOCK, forget, native


def configuration(body):
    """Validate exact provider fields without reflecting private input in errors."""
    allowed={"provider","store_app_id","account_id","key_id","issuer_id","client_id","private_key","id","version"}
    if set(body)-allowed or body.get("provider") not in ("app_store","apple_ads"):
        raise Invalid("Choose a supported provider and only the documented setup fields")
    result={key:required(body.get(key),key.replace("_"," "),120) for key in ("provider","key_id","issuer_id")}
    result["private_key"]=required(body.get("private_key"),"Private key file",2000)
    if not re.fullmatch(r"-----BEGIN PRIVATE KEY-----[\s\S]+-----END PRIVATE KEY-----",result["private_key"]):
        raise Invalid("Upload an unencrypted PKCS8 P-256 private PEM or .p8 key file")
    result["client_id"]=required(body.get("client_id"),"Apple Ads client ID",120) if result["provider"]=="apple_ads" else ""
    for key in ("key_id","issuer_id","client_id"):
        if result[key] and not re.fullmatch(r"[A-Za-z0-9.-]+",result[key]):
            raise Invalid("Provider identifiers may contain letters, numbers, dots and hyphens")
    return result


def identities(body):
    """Require explicit numeric promoted app and account before any key is stored."""
    result={"provider":body["provider"],"auth_mode":"managed_key"}
    for key in ("store_app_id","account_id"):
        value=body.get(key) or ("0" if key=="account_id" and body["provider"]=="app_store" else "")
        value=required(value,key.replace("_"," "),30)
        if not re.fullmatch(r"[0-9]+",value):
            raise Invalid("Store and account IDs must be numeric")
        result[key]=value
    return result


class Connections:
    def __init__(self,store):
        self.store=store
        self.scope=namespace(store.path)

    def name(self,app_id,data):
        """Compute protected target from current database and selected app identity."""
        return target(self.scope,app_id,data["provider"],data["credential_ref"])

    def record(self,app_id,record_id):
        """Resolve a connection only inside the selected app workspace."""
        record=next((r for r in self.store.records(app_id) if r["id"]==record_id and r["kind"]=="connection"),None)
        if not record:
            raise Invalid("Connection does not belong to this app")
        return record

    def setup(self,app_id,body):
        """Stage key, version-commit binding, clean failed stage and retire prior key."""
        self.store.app(app_id)
        config=configuration(body)
        data=identities(body)
        native("inspect",config["private_key"])
        with LOCK:
            previous=self.record(app_id,body["id"]) if body.get("id") else None
            if previous and (previous["version"]!=body.get("version") or previous["data"]["provider"]!=data["provider"]):
                raise Invalid("Connection changed; reload before rotating its key")
            data["credential_ref"]=uid()
            name=self.name(app_id,data)
            vault=Vault()
            vault.put(name,config)
            try:
                record=self.store.save_record(app_id,{"id":previous["id"] if previous else None,"version":body.get("version"),"kind":"connection",
                    "title":"Protected "+data["provider"]+" connection","source":"Local protected key setup; access remains untested","data":data})
            except Exception:
                vault.delete(name)
                raise
            cleanup=self.retire(vault,app_id,previous)
        return {"record":record,"status":"CONFIGURED_UNTESTED","cleanup":cleanup}

    def retire(self,vault,app_id,previous):
        """Retire only a previously referenced key; report cleanup failure truthfully."""
        if not previous or not previous["data"].get("credential_ref"):
            return "NO_PRIOR_KEY"
        name=self.name(app_id,previous["data"])
        forget(name)
        try:
            vault.delete(name)
            return "PRIOR_LOCAL_KEY_REMOVED"
        except Invalid:
            return "PRIOR_LOCAL_KEY_CLEANUP_REQUIRED"

    def disconnect(self,app_id,record_id,version):
        """Commit disabled access before retiring its key; failed saves preserve access."""
        with LOCK:
            record=self.record(app_id,record_id)
            if record["version"]!=version:
                raise Invalid("Connection changed; reload before disconnecting")
            data={**record["data"],"auth_mode":"disconnected"}
            self.store.save_record(app_id,{**record,"data":data})
            cleanup=self.retire(Vault(),app_id,record)
        return {"status":"DISCONNECTED","provider_revocation":"NOT_PERFORMED","cleanup":cleanup}

    def cleanup_status(self,app_id,data):
        """Report only local key presence after disconnection, including unreadable storage."""
        if not data.get("credential_ref"):
            return "NO_PROTECTED_KEY"
        try:
            return "REMOVAL_PENDING" if Vault().get(self.name(app_id,data)) else "NOT_PRESENT"
        except Invalid:
            return "UNCONFIRMED"

    def statuses(self,app_id):
        """Return presence only; never return private configuration or cached bearer."""
        result={}
        for record in self.store.records(app_id):
            if record["kind"]!="connection":
                continue
            data=record["data"]
            status="ENVIRONMENT_REFERENCE"
            if data.get("auth_mode")=="disconnected":
                status="DISCONNECTED"
            elif data.get("credential_ref"):
                try:
                    status="PROTECTED_KEY_PRESENT" if Vault().get(self.name(app_id,data)) else "RECONNECT_REQUIRED"
                except Invalid:
                    status="PROTECTED_STORAGE_UNAVAILABLE"
            result[record["id"]]={"status":status}
            if status=="DISCONNECTED":
                result[record["id"]]["cleanup"]=self.cleanup_status(app_id,data)
        return result
