"""Credential-free exact public reads; immutable history cannot authorize effects."""
import json
import re
from .common import Invalid, canonical, digest, now, iso_time
from .db import connection
from .action_contract import find
from .store import decode, audit
from .aeo_transport import PublicReader
from .public_store_page import destination, inspect


def body_data(body):
    """Reject fabricated scope, unsupported URLs and ambiguous request types."""
    if not isinstance(body,dict) or set(body)!={"manifest_version","action_hash","country"}:
        raise Invalid("Choose this action, current app version and a storefront country")
    if type(body["manifest_version"]) is not int or body["manifest_version"]<1:
        raise Invalid("Refresh the current app setup before checking its listing")
    if not isinstance(body["action_hash"],str) or not re.fullmatch(r"[a-f0-9]{64}",body["action_hash"]):
        raise Invalid("Inspect the exact action hash before checking its listing")
    if not isinstance(body["country"],str) or not re.fullmatch(r"[a-z]{2}",body["country"]):
        raise Invalid("Choose a two-letter lowercase storefront country, such as us or ca")
    return body


def exact_packet(db,app_id,identity,body):
    """Verify immutable action namespace and request digest."""
    row=find(db,app_id,identity);packet=json.loads(row["packet"])
    if digest(packet)!=row["hash"] or row["hash"]!=body["action_hash"] or packet.get("app_id")!=app_id or packet.get("operation")!="APP_STORE_PROMOTIONAL_TEXT":
        raise Invalid("Exact action integrity changed; reopen this app action")
    return row,packet


def exact_source(db,app_id,packet,version):
    """Require the exact current manifest and source record."""
    app=db.execute("SELECT * FROM apps WHERE id=?",(app_id,)).fetchone()
    source=db.execute("SELECT * FROM records WHERE app_id=? AND id=?",(app_id,packet["record"]["id"])).fetchone()
    manifest=decode(app)
    if source is None or decode(source)!=packet["record"] or manifest["version"]!=version or manifest["version"]!=packet["manifest_version"]:
        raise Invalid("App or store evidence changed; prepare current action evidence first")
    return manifest


def binding(db, app_id, identity, body):
    """Revalidate exact current product source without granting write authority."""
    body_data(body);row,packet=exact_packet(db,app_id,identity,body)
    manifest=exact_source(db,app_id,packet,body["manifest_version"])
    expected=packet["after"]
    if manifest["data"].get("release")!=expected["release"] or manifest["data"].get("locale")!=expected["locale"]:
        raise Invalid("App release or locale changed; reopen current evidence")
    app_id_text=expected["store_app_id"]
    if not isinstance(app_id_text,str) or not re.fullmatch(r"[0-9]{1,20}",app_id_text):
        raise Invalid("Action has no valid numeric App Store ID")
    return {"app_id":app_id,"manifest_version":manifest["version"],"manifest_hash":digest(manifest["data"]),"action_hash":row["hash"],
            "country":body["country"],"store_app_id":app_id_text,"release":expected["release"],"locale":expected["locale"],"copy":expected["promotional_text"]}


def history(db, app_id, identity):
    """Verify and return existing observations without creating a receipt."""
    find(db,app_id,identity);result=[]
    for row in db.execute("SELECT * FROM provider_action_events WHERE action_id=? ORDER BY id",(identity,)):
        data=json.loads(row["data"])
        if digest(data)!=row["hash"]:raise Invalid("Action receipt integrity changed")
        if data.get("state")=="PUBLIC_LISTING_CHECK":result.append({"id":row["id"],"hash":row["hash"],**data})
    return result


def availability(db, app_id, identity, event):
    """Fresh public observation and historical provider authorization stay separate."""
    bound=event["detail"]["binding"]
    try:
        current=binding(db,app_id,identity,{"manifest_version":bound["manifest_version"],"action_hash":bound["action_hash"],"country":bound["country"]})
        if current!=bound:return "STALE_SOURCE"
    except (Invalid,KeyError,TypeError):return "STALE_SOURCE"
    age=(iso_time(now())-iso_time(event["observed_at"])).total_seconds()
    return "CURRENT" if 0<=age<=86400 else "STALE_TIME"


class PublicStore:
    def __init__(self, store):
        """Use only the local mission-control persistence boundary."""
        self.store=store

    def list(self, app_id):
        """Bounded action history with currentness, never a publication claim."""
        self.store.app(app_id);result={}
        with connection(self.store.path) as db:
            for action in db.execute("SELECT id FROM provider_actions WHERE app_id=? ORDER BY created DESC LIMIT 100",(app_id,)):
                result[action["id"]]=[dict(event,evidence_status=availability(db,app_id,action["id"],event)) for event in history(db,app_id,action["id"])]
        return result

    def run(self, app_id, identity, body, reader=None):
        """Perform one safe read and commit only if exact source is unchanged."""
        with connection(self.store.path) as db:
            bound=binding(db,app_id,identity,body)
            if len(history(db,app_id,identity))>=100:raise Invalid("Public check history limit reached; download this action receipt")
        target=f'https://apps.apple.com/{bound["country"]}/app/id{bound["store_app_id"]}'
        try:
            reader=reader or PublicReader()
            resource=reader.read(target,1048576,permit=lambda u:destination(u,bound["country"],bound["store_app_id"]))
            report=inspect(resource,bound)
        except Exception:
            report={"status":"READ_UNAVAILABLE","reasons":["PUBLIC_READ_FAILED"],"checks":{},"language":None,"version":None,"resource":None}
        data={"state":"PUBLIC_LISTING_CHECK","observed_at":now(),"detail":{"binding":bound,"target":target,"report":report,
              "classification":"SERVER_RENDERED_HTTP_OBSERVATION_ONLY","provider_write":"NOT_RUN","attribution":"UNPROVEN","device_rendering":"NOT_VERIFIED","growth":"NOT_MEASURED"}}
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if binding(db,app_id,identity,body)!=bound:raise Invalid("App or action changed during read; saved inputs are preserved, reopen and check again")
            if len(history(db,app_id,identity))>=100:raise Invalid("Public check history limit reached")
            cursor=db.execute("INSERT INTO provider_action_events(action_id,data,hash,created) VALUES(?,?,?,?)",(identity,canonical(data),digest(data),data["observed_at"]))
            audit(db,app_id,"public_listing.checked",{"action_id":identity,"receipt_hash":digest(data),"status":report["status"]})
            result={"id":cursor.lastrowid,"hash":digest(data),**data,"evidence_status":"CURRENT"}
        return result
