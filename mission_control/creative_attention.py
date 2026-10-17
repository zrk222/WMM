"""Comparable observed attention only; no growth or confidence inference."""
import math
from statistics import median
from .common import iso_time

BUCKETS=(1,3,7,14,30,90)


def age_bucket(data):
    """Use publication age at observation, never age at import."""
    if not data["published_at"] or not data["metric_at"]:return None
    age=(iso_time(data["metric_at"])-iso_time(data["published_at"])).total_seconds()/86400
    return next((i for i,b in enumerate(BUCKETS) if age<b),len(BUCKETS))


def comparable_key(data):
    """Require known creator, traffic and observation before defining peers."""
    if data["traffic_class"]=="UNKNOWN" or not data["creator_id"] or data["metric_value"] is None:return None
    bucket=age_bucket(data)
    if bucket is None:return None
    return tuple(data[k] for k in ("platform","creator_id","metric_kind","traffic_class","locale","format"))+(bucket,)


def freshness(data,evaluated_at):
    """Disclose recency discount; old/missing observations stay unavailable."""
    if not data["metric_at"]:return None
    age=(iso_time(evaluated_at)-iso_time(data["metric_at"])).total_seconds()/86400
    if age<0 or age>90:return None
    return 2**(-age/30)


def velocity(source):
    """Two snapshots measure an observed interval, not future velocity."""
    rows=source["captures"]
    if len(rows)<2:return None
    before,after=(r["data"] for r in rows[-2:])
    if comparable_key(before) is None or comparable_key(after) is None:return None
    keys=("platform","post_id","creator_id","metric_kind","traffic_class","locale","format","published_at")
    if any(before[k]!=after[k] for k in keys):return None
    elapsed=(iso_time(after["metric_at"])-iso_time(before["metric_at"])).total_seconds()/86400
    delta=after["metric_value"]-before["metric_value"]
    if elapsed<=0 or delta<0:return None
    try:value=delta/elapsed
    except OverflowError:return None
    return value if math.isfinite(value) else None


def unavailable(reason,peers=None):
    """Preserve absent attention as null with denominator and repair reason."""
    return {"status":"UNAVAILABLE","score":None,"reason":reason,"n":len(peers or []),"peers":peers or []}


def peer_values(target,sources,evaluated_at,mode):
    """Select comparable current posts from the explicitly selected pool."""
    d=target["current"]["data"];key=comparable_key(d);peers=[]
    for source in sources:
        p=source["current"]["data"]
        if source["id"]==target["id"] or comparable_key(p)!=key:continue
        if abs((iso_time(p["metric_at"])-iso_time(d["metric_at"])).total_seconds())>90*86400:continue
        value=p["metric_value"] if mode=="cumulative" else velocity(source)
        if freshness(p,evaluated_at) is None or value is None:continue
        peers.append({"id":source["id"],"hash":source["current"]["hash"],"value":value,"observed_at":p["metric_at"]})
    return peers


def robust_attention(value,peers,discount):
    """Robust log exploratory score, explicitly not a success probability."""
    if len(peers)<5:return unavailable("At least 5 comparable peer posts are required",peers)
    logs=[log_observation(p["value"]) for p in peers];center=median(logs)
    mad=median([abs(x-center) for x in logs])
    if mad==0:return unavailable("Comparable peer variation is zero",peers)
    raw_z=(log_observation(value)-center)/(1.4826*mad)
    shrink=len(peers)/(len(peers)+10);z=max(-5,min(5,raw_z))*shrink
    return {"status":"OBSERVED_COMPARISON","score":max(0,z/5)*discount,"raw_z":raw_z,"shrunk_z":z,
            "n":len(peers),"log_median":center,"log_mad":mad,"shrinkage":shrink,"freshness":discount,"peers":peers,
            "window_days":90,"reason":"Selected-pool comparison; not calibrated confidence or ROI"}


def log_observation(value):
    """Keep integer counts finite on the log scale without overflowing float conversion."""
    return math.log(value+1) if type(value) is int else math.log1p(value)


def attention(target,sources,evaluated_at,mode="cumulative"):
    """Keep cumulative/velocity denominators distinct and missingness explicit."""
    d=target["current"]["data"]
    if comparable_key(d) is None:return unavailable("Known creator, traffic, metric and publication age required")
    discount=freshness(d,evaluated_at)
    if discount is None:return unavailable("Observation missing, future or older than 90 days")
    value=d["metric_value"] if mode=="cumulative" else velocity(target)
    if value is None:return unavailable("Two comparable increasing-time captures required for velocity")
    return robust_attention(value,peer_values(target,sources,evaluated_at,mode),discount)
