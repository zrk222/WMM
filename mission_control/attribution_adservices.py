"""Fixed read-only AdServices transport with single-use ephemeral tokens and declared SDK scope."""
import hashlib
import json
import re
import time
import urllib.request
from .common import Invalid,canonical,digest,iso_time,now,uid
from .db import connection
from .review_access import member
from .payment_signature import unique_pairs,bounded_tree
from . import attribution_contract as contract
from .attribution_sources import source,current_authority
from .attribution_ingestion import commit,failure,room

ENDPOINT="https://api-adservices.apple.com/api/v1/"
CAP=2097152
RESPONSE_FIELDS=("orgId","campaignId","adGroupId","keywordId","adId","conversionType","claimType",
                 "clickDate","impressionDate","countryOrRegion","supplyPlacement")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        """A token may never follow a provider redirect to another endpoint."""
        raise Invalid("AdServices redirects are not permitted")


def transport(token):
    """Post only to Apple's fixed HTTPS endpoint; never persist the token."""
    request=urllib.request.Request(ENDPOINT,data=token.encode("ascii"),method="POST",
                                   headers={"Content-Type":"text/plain","Accept":"application/json"})
    opener=urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=15) as response:
            if response.geturl()!=ENDPOINT or response.status!=200:raise Invalid("AdServices response status is unavailable")
            payload=response.read(CAP+1)
    except Exception:
        raise Invalid("AdServices read failed; obtain a fresh SDK token after checking app setup and network access") from None
    if not 0<len(payload)<=CAP:raise Invalid("AdServices response exceeds its limit")
    try:
        data=json.loads(payload.decode("utf-8"),object_pairs_hook=unique_pairs)
        bounded_tree(data)
    except (ValueError,UnicodeError,RecursionError):
        raise Invalid("AdServices returned invalid JSON") from None
    if not isinstance(data,dict):raise Invalid("AdServices returned no attribution object")
    return data


def input_token(body,clock=None):
    """Validate explicit single-read consent and the SDK token's strict one-day lifetime."""
    contract.fields(body,("token","obtained_at","confirm_read"))
    if body["confirm_read"] is not True:raise Invalid("Confirm one AdServices attribution read")
    token=body["token"]
    if not isinstance(token,str) or not 0<len(token)<=16384 or not re.fullmatch(r"[!-~]+",token):
        raise Invalid("Enter a bounded opaque ASCII SDK token")
    obtained=iso_time(body["obtained_at"]).timestamp()
    age=(time.time() if clock is None else clock)-obtained
    if not 0<=age<86400:raise Invalid("Obtain a fresh SDK token less than 24 hours old")
    return token,hashlib.sha256(token.encode("ascii")).hexdigest()


def response_fields(data,config):
    """Normalize a closed documented response without inventing organic attribution."""
    contract.fields(data,("attribution",),RESPONSE_FIELDS)
    contract.boolean(data["attribution"])
    facts={"attribution":data["attribution"]}
    if data["attribution"] and "orgId" not in data:raise Invalid("Attributed response has no organization")
    for field in ("orgId","campaignId","adGroupId","keywordId","adId"):
        if data.get(field) is not None:
            facts[field]=contract.integer(data[field],1,9223372036854775807)
    if "orgId" in facts and facts["orgId"]!=int(config["org_id"]):raise Invalid("AdServices organization differs from this source")
    optional_claims(data,facts)
    optional_strings(data,facts)
    return facts


def optional_claims(data,facts):
    """Keep supported claim/conversion types and explicit provider timestamps."""
    for field,allowed in (("claimType",("Click","Impression")),("conversionType",("Download","Redownload","PreOrder"))):
        if data.get(field) is not None:
            if data[field] not in allowed:raise Invalid("AdServices claim/conversion type is unsupported")
            facts[field]=data[field]
    for field in ("clickDate","impressionDate"):
        if data.get(field) is not None:
            iso_time(data[field]);facts[field]=data[field]


def optional_strings(data,facts):
    """Retain bounded provider placement and country metadata without added meaning."""
    country=data.get("countryOrRegion")
    if country is not None:
        if not isinstance(country,str) or not re.fullmatch(r"[A-Z]{2}",country):raise Invalid("AdServices country is invalid")
        facts["countryOrRegion"]=country
    placement=data.get("supplyPlacement")
    if placement is not None:
        if not isinstance(placement,str) or not re.fullmatch(r"[A-Z0-9_]{1,80}",placement):raise Invalid("AdServices placement is invalid")
        facts["supplyPlacement"]=placement


def observation(data,config,token_hash):
    """No authenticated advertised-app ID exists in the response; SDK binding is declared."""
    facts=response_fields(data,config)
    conversion={"Download":"download","Redownload":"redownload","PreOrder":"preorder"}.get(facts.get("conversionType"))
    return {"channel":"AdServices","environment":config["environment"],"app_id":int(config["app_apple_id"]),
            "identity":digest({"channel":"AdServices","environment":config["environment"],"token_sha256":token_hash,
                               "app_id":config["app_apple_id"]}),
            "facts":facts,"attribution":facts["attribution"],"conversion_type":conversion,
            "new_install_candidate":facts["attribution"] and conversion=="download",
            "app_binding":"DECLARED_SDK_SCOPE","transport_provenance":"API_RETRIEVED",
            "organic_status":"UNKNOWN","overlap_status":"UNRESOLVED","current_ingestion_authority":False}


class AdServices:
    def __init__(self,store):self.store=store

    def reserve(self,app,sid,user,token_hash,obtained_at):
        """Consume the digest atomically before transport, including failed calls."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            original=source(db,app,sid);role=member(db,app,user["principal"],"MAKER")
            if original["data"]["channel"]!="AdServices":raise Invalid("Use an AdServices source")
            if db.execute("SELECT 1 FROM attribution_reads WHERE app_id=? AND id=?",(app,token_hash)).fetchone():
                raise Invalid("This token was already attempted; obtain a fresh SDK token")
            room(db,app)
            data={"digest":token_hash,"obtained_at":iso_time(obtained_at).isoformat(),"source_hash":original["hash"],
                  "source_version":original["version"],"status":"PENDING"}
            db.execute("INSERT INTO attribution_reads VALUES(?,?,?,?,?,?,?,?)",
                       (app,token_hash,sid,canonical(data),digest(data),"PENDING",0,now()))
        return original,role

    def finish_read(self,app,sid,token_hash,status):
        """Keep a sanitized terminal request state even if authority changed during transport."""
        with connection(self.store.path) as db:
            row=db.execute("SELECT data FROM attribution_reads WHERE app_id=? AND id=?",(app,token_hash)).fetchone()
            data=json.loads(row["data"]);data["status"]=status
            db.execute("UPDATE attribution_reads SET data=?,hash=?,status=? WHERE app_id=? AND id=?",
                       (canonical(data),digest(data),status,app,token_hash))

    def read(self,app,sid,user,body):
        """Perform exactly one permitted read; recheck role and source before saving facts."""
        self.store.app(app)
        token,token_hash=input_token(body)
        original,role=self.reserve(app,sid,user,token_hash,body["obtained_at"])
        try:
            data=transport(token)
            normalized=observation(data,original["data"],token_hash)
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                current=current_authority(db,app,sid,original,user,role)
                result=commit(db,app,current,None,normalized,token_hash,"API_RETRIEVED_DECLARED_SDK_SCOPE")
            self.finish_read(app,sid,token_hash,"SUCCEEDED")
            return result
        except Exception:
            self.finish_read(app,sid,token_hash,"FAILED")
            failure(self.store,app,sid,token_hash,"ADSERVICES_READ_FAILED")
            raise Invalid("AdServices read failed. Check the declared app and organization, then obtain a fresh SDK token; prior input is not stored.") from None
