"""Permitted app-scoped source references; untrusted source text never executes."""
import csv
import io
import ipaddress
import json
from datetime import timezone
from urllib.parse import urlsplit,parse_qs
from .common import Invalid,amount,canonical,digest,iso_time,now,required,safe_data,uid
from .db import connection
from .ledger import opaque

FIELDS={"platform","post_id","title","url","source","captured_at","published_at","locale","traffic_class","creator_id","format","metric_kind","metric_value","metric_at","rights","permission_confirmed","topic","relevance_note"}
ENUMS={"platform":{"tiktok","youtube","instagram","linkedin","x","other"},"traffic_class":{"ORGANIC","PAID","UNKNOWN"},"rights":{"REFERENCE_ONLY","LICENSED","UNKNOWN"},"metric_kind":{"VIEWS","LIKES","SHARES","UNKNOWN"}}


def source_url(value):
    """Accept public HTTPS reference links without fetching arbitrary destinations."""
    value=required(value,"Source URL",2000);p=urlsplit(value);host=p.hostname or ""
    try:port=p.port
    except ValueError as exc:raise Invalid("Invalid source URL port") from exc
    if p.scheme!="https" or not host or p.username is not None or p.password is not None or port is not None or p.fragment:raise Invalid("Use a public HTTPS link without credentials, custom port or fragment")
    source_host(host)
    if {k.lower() for k in parse_qs(p.query)}&{"token","access_token","api_key","password","secret","signature"}:raise Invalid("Remove private authorization parameters from the source URL")
    return value


def source_host(host):
    """Reject local and ambiguous host literals without resolving or fetching DNS."""
    host=host.rstrip(".")
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        if host=="localhost" or host.endswith((".localhost",".local",".internal")) or "." not in host:raise Invalid("Local source destinations are not permitted")
        if all(c in "0123456789." for c in host):raise Invalid("Ambiguous numeric source host")
    else:
        if not address.is_global:raise Invalid("Private or loopback source destinations are not permitted")


def reference_data(data):
    """Normalize exact permission/provenance fields without inferring missing observations."""
    safe_data(data)
    if set(data)!=FIELDS:raise Invalid("Complete the source fields; unsupported columns are rejected")
    result=dict(data)
    for key,choices in ENUMS.items():
        if data[key] not in choices:raise Invalid("Choose a valid "+key.replace("_"," "))
    if data["permission_confirmed"] is not True:raise Invalid("Confirm permission to store this source before importing")
    bounds={"title":200,"source":2000,"locale":120,"format":120,"topic":200,"relevance_note":2000}
    for key,bound in bounds.items():result[key]=required(data[key],key.replace("_"," "),bound)
    result["post_id"]=opaque(data["post_id"],"Public post ID")
    result["creator_id"]=opaque(data["creator_id"],"Public creator ID") if data["creator_id"] is not None else None
    result["url"]=source_url(data["url"])
    reference_dates(result)
    if result["metric_value"] is not None:
        amount(result["metric_value"],"Observed count")
        if result["metric_kind"]=="UNKNOWN" or result["metric_at"] is None:raise Invalid("Observed counts need a known metric and timestamp")
    return result


def reference_dates(data):
    """Validate timezone and chronology; unknown publication/observation stays unknown."""
    for key in ("captured_at","published_at","metric_at"):
        if data[key] is None and key!="captured_at":continue
        stamp=iso_time(data[key]).astimezone(timezone.utc)
        if stamp>iso_time(now()):raise Invalid("Source observations cannot be dated in the future")
        data[key]=stamp.isoformat()
    date_order(data)


def date_order(data):
    """A captured observation cannot predate its own published or measured source."""
    capture=iso_time(data["captured_at"])
    for key in ("published_at","metric_at"):
        if data[key] and iso_time(data[key])>capture:raise Invalid("Publication and metrics cannot follow their capture")
    if data["published_at"] and data["metric_at"] and iso_time(data["metric_at"])<iso_time(data["published_at"]):raise Invalid("Metric cannot precede publication")


def identity(data):
    """Retain exact platform/post identity independently of title, metrics or URLs."""
    return data["platform"]+":"+data["post_id"]


def latest_capture(db,app_id,reference_id):
    """Resolve the current immutable capture within this app only."""
    row=db.execute("SELECT * FROM creative_captures WHERE app_id=? AND reference_id=? ORDER BY version DESC LIMIT 1",(app_id,reference_id)).fetchone()
    if not row:raise Invalid("Reference does not belong to this app")
    result=dict(row);result["data"]=json.loads(result["data"])
    return result


def append_capture(db,app_id,reference_id,data,version):
    """Append a source-bound capture and audit receipt in the same transaction."""
    count=db.execute("SELECT count(*) FROM creative_captures WHERE app_id=?",(app_id,)).fetchone()[0]
    if count>=5000:raise Invalid("Archive this workspace before exceeding 5000 captures")
    stamp=now();value_hash=digest(data)
    db.execute("INSERT INTO creative_captures VALUES(?,?,?,?,?,?)",(app_id,reference_id,version,canonical(data),value_hash,stamp))
    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,"creative.captured",canonical({"reference_id":reference_id,"version":version,"hash":value_hash}),stamp))


def write_reference(db,app_id,data):
    """Create source identity once; conflicting duplicates require explicit refresh."""
    old=db.execute("SELECT id FROM creative_references WHERE app_id=? AND identity=?",(app_id,identity(data))).fetchone()
    if old:
        current=latest_capture(db,app_id,old["id"])
        if current["hash"]!=digest(data):raise Invalid("This post already exists with different observations; inspect and Refresh it")
        return {"id":old["id"],"status":"UNCHANGED"}
    if db.execute("SELECT count(*) FROM creative_references WHERE app_id=?",(app_id,)).fetchone()[0]>=1000:raise Invalid("Workspace source limit is 1000 references")
    reference_id=uid()
    db.execute("INSERT INTO creative_references VALUES(?,?,?)",(app_id,reference_id,identity(data)))
    append_capture(db,app_id,reference_id,data,1)
    return {"id":reference_id,"status":"SAVED"}


def import_rows(body):
    """Parse bounded permitted exports with exact columns and honest nullable fields."""
    if set(body)=={"csv"}:
        reader=csv.DictReader(io.StringIO(required(body["csv"],"CSV export",1048576).lstrip("\ufeff")))
        fields=reader.fieldnames or []
        if len(fields)!=len(set(fields)) or set(fields)!=FIELDS:raise Invalid("CSV needs the template columns, without duplicates")
        rows=[csv_reference(row) for row in reader]
    elif set(body)=={"rows"}:rows=body["rows"]
    else:raise Invalid("Choose one permitted CSV or JSON row export")
    if not isinstance(rows,list) or not 1<=len(rows)<=100:raise Invalid("Import 1 through 100 sources per batch")
    normalized=[reference_data(row) for row in rows]
    if len({identity(row) for row in normalized})!=len(normalized):raise Invalid("Remove duplicate posts from this import")
    return normalized


def csv_reference(row):
    """Convert only explicitly known CSV scalar types; blanks remain null."""
    if set(row)!=FIELDS:raise Invalid("Malformed CSV row")
    result=dict(row)
    for key in ("published_at","creator_id","metric_value","metric_at"):
        if result[key]=="":result[key]=None
    if result["permission_confirmed"] not in ("true","false"):raise Invalid("CSV permission must be true or false")
    result["permission_confirmed"]=result["permission_confirmed"]=="true"
    if result["metric_value"] is not None:
        if not result["metric_value"].isdigit():raise Invalid("CSV metric must be a whole nonnegative count or blank")
        result["metric_value"]=int(result["metric_value"])
    return result


class Library:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Return current sources plus immutable capture history, never fabricated metrics."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=[dict(r) for r in db.execute("SELECT * FROM creative_references WHERE app_id=? ORDER BY identity",(app_id,))]
            for row in rows:
                captures=[]
                for r in db.execute("SELECT * FROM creative_captures WHERE app_id=? AND reference_id=? ORDER BY version",(app_id,row["id"])):
                    item=dict(r);item["data"]=json.loads(item["data"]);captures.append(item)
                row["captures"]=captures;row["current"]=captures[-1]
            return rows

    def save(self,app_id,body):
        """Create or explicitly refresh with optimistic version and immutable identity."""
        self.store.app(app_id)
        if set(body) not in ({"data"},{"id","version","data"}):raise Invalid("Invalid source save fields")
        data=reference_data(body["data"])
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if "id" not in body:return write_reference(db,app_id,data)
            current=latest_capture(db,app_id,body["id"])
            if type(body["version"]) is not int or current["version"]!=body["version"]:raise Invalid("Reference changed; reload before refreshing")
            if identity(current["data"])!=identity(data):raise Invalid("Refresh cannot change this source identity")
            if iso_time(data["captured_at"])<iso_time(current["data"]["captured_at"]):raise Invalid("Refresh cannot backdate the latest capture")
            if current["hash"]==digest(data):return {"id":body["id"],"status":"UNCHANGED"}
            append_capture(db,app_id,body["id"],data,current["version"]+1)
            return {"id":body["id"],"status":"REFRESHED"}

    def preview(self,app_id,body):
        """Preview provenance, unknown values and conflicts before explicit atomic commit."""
        self.store.app(app_id);rows=import_rows(body);existing={r["identity"]:r for r in self.list(app_id)}
        conflicts=[identity(r) for r in rows if identity(r) in existing and existing[identity(r)]["current"]["hash"]!=digest(r)]
        return {"rows":rows,"preview_hash":digest(rows),"conflicts":conflicts,"provenance":"OPERATOR_IMPORT; permission and observations are supplied, not independently verified"}

    def commit(self,app_id,body):
        """Revalidate preview and commit every source or none under a write transaction."""
        self.store.app(app_id)
        if set(body)!={"rows","preview_hash"}:raise Invalid("Commit the exact previewed export")
        rows=import_rows({"rows":body["rows"]})
        if digest(rows)!=body["preview_hash"]:raise Invalid("Import preview changed; preview again")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            return {"results":[write_reference(db,app_id,row) for row in rows],"provenance":"OPERATOR_IMPORT"}


def export_library(store,app_id):
    """Export exact immutable references without redundant derived current fields."""
    return [{k:v for k,v in row.items() if k!="current"} for row in Library(store).list(app_id)]


def restore_library(db,app_id,items):
    """Validate every source capture and scoped contiguous version before restore."""
    if items is None:return
    library_snapshot(items)
    seen=set()
    for row in items:
        restore_reference(db,app_id,row,seen)


def library_snapshot(items):
    """Bound portable collections and require capture lists before calculating totals."""
    if not isinstance(items,list) or len(items)>1000:raise Invalid("Invalid reference collection")
    if any(not isinstance(row,dict) or not isinstance(row.get("captures"),list) for row in items):raise Invalid("Invalid reference capture schema")
    if sum(len(row["captures"]) for row in items)>5000:raise Invalid("Too many source captures")


def restore_reference(db,app_id,row,seen):
    """Restore one scoped source and its immutable capture sequence in caller transaction."""
    if set(row)!={"app_id","id","identity","captures"} or row["app_id"]!=app_id:raise Invalid("Reference snapshot scope or schema mismatch")
    opaque(row["id"],"Reference ID")
    if row["id"] in seen or row["identity"] in seen:raise Invalid("Duplicate restored source")
    seen.update((row["id"],row["identity"]))
    if not row["captures"]:raise Invalid("Reference has no capture history")
    db.execute("INSERT INTO creative_references VALUES(?,?,?)",(app_id,row["id"],row["identity"]))
    previous=None
    for version,item in enumerate(row["captures"],1):
        data=restore_capture(row,item,version,previous);previous=data
        db.execute("INSERT INTO creative_captures VALUES(?,?,?,?,?,?)",(app_id,row["id"],version,canonical(data),item["hash"],item["created"]))


def restore_capture(row,item,version,previous):
    """Check content hashes, identity, chronology and exact owner for every capture."""
    if set(item)!={"app_id","reference_id","version","data","hash","created"} or item["app_id"]!=row["app_id"] or item["reference_id"]!=row["id"]:raise Invalid("Source capture scope or schema mismatch")
    data=reference_data(item["data"])
    if type(item["version"]) is not int or item["version"]!=version or identity(data)!=row["identity"] or digest(data)!=item["hash"]:raise Invalid("Source capture identity, version or hash mismatch")
    iso_time(item["created"])
    if previous and iso_time(data["captured_at"])<iso_time(previous["captured_at"]):raise Invalid("Source capture history goes backwards")
    return data
