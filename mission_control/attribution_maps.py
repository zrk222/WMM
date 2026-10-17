"""Immutable explicit release/locale conversion-map versions with no inferred money."""
import re
from .common import Invalid,canonical,digest,iso_time,now,required,safe_data,uid
from .db import connection
from .review_access import member
from .store import audit
from . import attribution_contract as contract
from .attribution_sources import checked


def labels(rows,coarse=False):
    """Validate bounded unique symbolic labels, preserving fine zero as an actual value."""
    cap=3 if coarse else 64
    if not isinstance(rows,list) or len(rows)>cap:raise Invalid("Conversion labels exceed their limit")
    result=[]
    for row in rows:
        contract.fields(row,("value","label"))
        value=row["value"]
        if coarse:
            if value not in ("low","medium","high"):raise Invalid("Choose a recognized coarse value")
        else:contract.integer(value,0,63)
        result.append({"value":value,"label":required(row["label"],"Symbolic label",180)})
    if len({r["value"] for r in result})!=len(result):raise Invalid("Conversion values must be unique")
    return result


def declaration(body):
    """Bind symbolic meanings to exact release, locale, channel and sequence."""
    contract.fields(body,("release","locale","channel","sequence","effective_at","fine","coarse","original_source"))
    safe_data(body)
    if body["channel"] not in ("SKAdNetwork","AdAttributionKit"):raise Invalid("Conversion maps apply to SKAN or AdAttributionKit")
    contract.integer(body["sequence"],0,2)
    locale=required(body["locale"],"Locale",35)
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*",locale):raise Invalid("Use a language-region locale")
    fine=labels(body["fine"])
    if body["sequence"] and fine:raise Invalid("Fine conversion labels apply only to sequence zero")
    return {"release":required(body["release"],"Release",120),"locale":locale,"channel":body["channel"],
            "sequence":body["sequence"],"effective_at":iso_time(body["effective_at"]).isoformat(),
            "fine":fine,"coarse":labels(body["coarse"],True),
            "original_source":required(body["original_source"],"Original mapping source",1000)}


def mapping(db,app,mid,version,expected_hash,channel=None):
    """Use the selected immutable version, never the latest version implicitly."""
    contract.integer(version,1,1000000)
    row=db.execute("SELECT * FROM attribution_maps WHERE app_id=? AND id=? AND version=?",(app,mid,version)).fetchone()
    if not row:raise KeyError("Conversion map version not found")
    result=checked(row)
    if result["hash"]!=expected_hash:raise Invalid("Conversion map hash changed; select it again")
    if result["imported"]:raise Invalid("Historical mapping has no current ingestion authority")
    if channel and result["data"]["channel"]!=channel:raise Invalid("Mapping belongs to a different attribution channel")
    if iso_time(result["data"]["effective_at"])>iso_time(now()):raise Invalid("Mapping is not effective yet")
    return result


class Maps:
    def __init__(self,store):self.store=store

    def list(self,app):
        """Retain every map revision; later changes cannot reinterpret earlier receipts."""
        self.store.app(app)
        with connection(self.store.path) as db:
            return [checked(r) for r in db.execute("SELECT * FROM attribution_maps WHERE app_id=? ORDER BY created DESC,version DESC",(app,))]

    def save(self,app,user,body):
        """Append a version with an optimistic previous-version check."""
        self.store.app(app)
        contract.fields(body,("id","expected_version","data"))
        data=declaration(body["data"]);mid=body["id"] or uid()
        contract.postback_id(mid);contract.integer(body["expected_version"],0,1000000)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");member(db,app,user["principal"],"MAKER")
            if db.execute("SELECT COUNT(*) FROM attribution_maps WHERE app_id=?",(app,)).fetchone()[0]>=100:
                raise Invalid("Conversion map history reached 100 versions")
            previous=db.execute("SELECT * FROM attribution_maps WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1",(app,mid)).fetchone()
            expected=previous["version"] if previous else 0
            if expected!=body["expected_version"]:raise Invalid("Mapping changed; reload before saving a new version")
            revision_allowed(previous,data)
            version=expected+1
            db.execute("INSERT INTO attribution_maps VALUES(?,?,?,?,?,?,?)",(app,mid,version,canonical(data),digest(data),0,now()))
            audit(db,app,"attribution.mapping_version_saved",{"id":mid,"version":version,"hash":digest(data)})
        return next(r for r in self.list(app) if r["id"]==mid and r["version"]==version)


def revision_allowed(previous,data):
    """Only append changed current maps; imported versions remain immutable history."""
    if previous and previous["imported"]:raise Invalid("Create a new map; imported versions stay historical")
    if previous and checked(previous)["data"]==data:raise Invalid("No mapping values changed")
