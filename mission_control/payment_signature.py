"""Exact-byte Stripe snapshot authentication and bounded, sanitized event decoding."""
import hashlib
import hmac
import json
import math
import re
import time
from .common import Invalid, digest

SUPPORTED={"charge.succeeded","refund.created","refund.updated","refund.failed"}


def object_id(value,prefix):
    """Accept only bounded opaque provider identifiers, never a URL or contact."""
    if not isinstance(value,str) or not re.fullmatch(prefix+r"_[A-Za-z0-9_]{1,110}",value):
        raise Invalid("Payment object identity is invalid")
    return value


def unique_pairs(pairs):
    """Reject duplicate JSON names before any ambiguous value is trusted."""
    result={}
    for key,value in pairs:
        if key in result:raise Invalid("Payment JSON has duplicate keys")
        result[key]=value
    return result


def bounded_tree(value,depth=0):
    """Limit nesting and reject nonfinite values without retaining private fields."""
    if depth>20:raise Invalid("Payment JSON nesting exceeds 20 levels")
    if isinstance(value,float) and not math.isfinite(value):raise Invalid("Payment JSON number is not finite")
    children=value.values() if isinstance(value,dict) else value if isinstance(value,list) else ()
    for item in children:bounded_tree(item,depth+1)


def strict_json(raw):
    """Decode a bounded exact UTF-8 object with no duplicate/nonfinite JSON values."""
    if not isinstance(raw,bytes) or not 0<len(raw)<=262144:raise Invalid("Payment body must be 1 through 262144 bytes")
    try:
        result=json.loads(raw.decode("utf-8"),object_pairs_hook=unique_pairs)
        bounded_tree(result)
    except (ValueError,UnicodeError,RecursionError) as exc:
        raise Invalid("Payment JSON is invalid") from exc
    if not isinstance(result,dict):raise Invalid("Payment body must be a JSON object")
    return result


def signature_parts(header):
    """Require one unambiguous timestamp and a bounded set of SHA256 v1 candidates."""
    if not isinstance(header,str) or not 0<len(header)<=4096:raise PermissionError("Payment signature is missing or invalid")
    parts=[part.strip().split("=",1) for part in header.split(",")]
    if any(len(part)!=2 for part in parts):raise PermissionError("Payment signature format is invalid")
    times=[v for k,v in parts if k=="t"];signatures=[v for k,v in parts if k=="v1"]
    if len(times)!=1 or not re.fullmatch(r"[0-9]{1,12}",times[0]):raise PermissionError("Payment signature timestamp is invalid")
    if not 1<=len(signatures)<=8 or any(not re.fullmatch(r"[a-fA-F0-9]{64}",v) for v in signatures):raise PermissionError("Payment v1 signature is invalid")
    return int(times[0]),signatures


def verify(raw,header,secret,clock=None):
    """Authenticate exact raw bytes using constant-time comparisons and a fixed age."""
    if not isinstance(raw,bytes) or not 0<len(raw)<=262144:raise Invalid("Payment body must be 1 through 262144 bytes")
    stamp,signatures=signature_parts(header)
    if abs((time.time() if clock is None else clock)-stamp)>300:raise PermissionError("Payment signature is outside the 300 second window")
    expected=hmac.new(secret.encode(),str(stamp).encode()+b"."+raw,hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected,value.lower()) for value in signatures):raise PermissionError("Payment signature verification failed")
    return stamp


def event_scope(event,config):
    """Bind the signed snapshot to the declared direct-account API version and mode."""
    if event.get("object")!="event" or event.get("account") is not None:raise Invalid("Use a direct-account snapshot event")
    if type(event.get("livemode")) is not bool or event["livemode"]!=config["livemode"]:raise Invalid("Payment environment does not match this source")
    if event.get("api_version")!=config["api_version"]:raise Invalid("Payment API version differs; review endpoint setup")
    created=event.get("created")
    if type(created) is not int or not 0<created<=time.time()+300:raise Invalid("Payment event time is invalid")
    name=event.get("type")
    if not isinstance(name,str) or not re.fullmatch(r"[a-z_.]{1,120}",name):raise Invalid("Payment event type is invalid")
    return object_id(event.get("id"),"evt"),name,created


def normalize(raw,config,app_id):
    """Keep only approved payment identities/hashes; discard all customer information."""
    event=strict_json(raw);eid,kind,created=event_scope(event,config)
    result={"event_id":eid,"event_type":kind,"event_created":created,"livemode":event["livemode"],
            "body_sha256":hashlib.sha256(raw).hexdigest(),"content_sha256":digest(event),
            "object_id":None,"charge_id":None,"candidate":kind in SUPPORTED}
    if kind not in SUPPORTED:return result
    obj,expected=snapshot_object(event,kind,app_id)
    result["object_id"]=object_id(obj.get("id"),"ch" if expected=="charge" else "re")
    result["charge_id"]=result["object_id"] if expected=="charge" else object_id(obj.get("charge"),"ch")
    return result


def snapshot_object(event,kind,app_id):
    """Validate supported object shape and optional explicit app ownership."""
    section=event.get("data")
    if not isinstance(section,dict):raise Invalid("Payment data section is missing")
    obj=section.get("object")
    if not isinstance(obj,dict):raise Invalid("Payment snapshot object is missing")
    expected="charge" if kind=="charge.succeeded" else "refund"
    if obj.get("object")!=expected:raise Invalid("Payment snapshot object type does not match")
    metadata=obj.get("metadata") or {}
    if not isinstance(metadata,dict):raise Invalid("Payment metadata shape is invalid")
    if metadata.get("growth_app_id",app_id)!=app_id:raise Invalid("Payment belongs to another app")
    return obj,expected
