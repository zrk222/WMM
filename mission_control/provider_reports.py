"""Bounded source-linked customer reviews and current Apple Ads report reads."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
import time
from urllib.parse import urlencode,urlsplit
from .common import Invalid,digest,iso_time,now,required
from .providers import credential,report_request
from .ads_reports import REPORT_PATHS, read_keywords
from .subscription_catalog import read_catalog
from .release_inventory import read_inventory, release_options
from .apple_analytics import identity as analytics_identity, read_analytics
from .apple_segments import read_instance_segments
from .apple_metrics import parse_partitions


@dataclass(frozen=True)
class PreparedAppleMetrics:
    """Validated report data awaiting atomic worker persistence and completion."""
    identity: dict
    partitions: tuple
    connection_hash: str
    metadata_source_hash: str
    operation: str = 'analytics_metrics'

    def summary(self, statuses):
        """Return bounded, secret-free job evidence after persistence commits."""
        values=[]
        for item,status in zip(self.partitions,statuses):
            instance=item['instance']
            values.append(dict(event_date=item['partition']['event_date'], status=status,
                observation_count=len(instance['rows']), source_count=len(instance['sources']),
                source_hash=digest(sorted(instance['sources'],key=lambda source:source['id']))))
        return dict(operation=self.operation,provider='app_store',
            app_id=self.identity['app_id'],store_app_id=self.identity['store_app_id'],
            report_id=self.identity['report_id'],report_family=self.identity['report_family'],
            granularity=self.identity['granularity'],coverage='COMPLETE',
            processing_date=self.partitions[0]['instance']['processing_date'],
            observed_at=now(),partition_count=len(values),
            observation_count=sum(item['observation_count'] for item in values),
            partitions=values,metadata_source_hash=self.metadata_source_hash,
            external_writes=False,event_data_finality='UNKNOWN',
            interpretation='Download events are not installs, sales, revenue, or measured lift.')


def report_options(provider,options):
    """Validate supported read operations and report dates before queue or network."""
    if not isinstance(options,dict):
        raise Invalid("Choose a report operation")
    operation=options.get("operation")
    if provider=='google_play':
        return google_options(options)
    if operation == 'release_inventory':
        return release_options(provider, options)
    if operation in ("reviews", "subscription_catalog", "analytics_reports") and provider=="app_store" and set(options)=={"operation"}:
        return options
    if operation=='analytics_metrics_latest' and provider=='app_store' and set(options)=={'operation','report_id'}:
        analytics_identity(options['report_id'])
        return options
    if operation=='analytics_metrics' and provider=='app_store' and set(options)=={'operation','report_id','instance_id'}:
        analytics_identity(options['report_id']);analytics_identity(options['instance_id'])
        return options
    if operation not in ("campaign_report", *REPORT_PATHS) or provider!="apple_ads" or set(options)!={"operation","start","end","campaign_ids"}:
        raise Invalid("Choose customer reviews or a dated Apple Ads campaign, keyword or search-term report")
    report_dates(options)
    campaign_ids(options["campaign_ids"])
    return options


def google_options(options):
    """Google reads have one closed operation field and no edit or purchase parameters."""
    from .play_contract import operation as play_operation
    if set(options)!={'operation'}:raise Invalid('Use only the selected Google Play read operation')
    play_operation(options['operation'])
    return options


def report_dates(options):
    """Validate chronological UTC dates within the supported daily lookback."""
    try:
        start,end=(date.fromisoformat(required(options[key],key,30)) for key in ("start","end"))
    except ValueError as exc:
        raise Invalid("Use ISO calendar dates") from exc
    today=datetime.now(timezone.utc).date()
    if start>end or end>today or (today-start).days>=90:
        raise Invalid("Choose a past report window within the last 90 days")


def campaign_ids(ids):
    """Require a finite list of distinct numeric campaign identities."""
    if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(v,str) or not re.fullmatch(r"\d{1,30}",v) for v in ids) or len(set(ids))!=len(ids):
        raise Invalid("Choose 1 to 20 distinct numeric campaign IDs")


class Reader:
    def __init__(self,headers):
        self.headers=headers
        self.deadline=time.monotonic()+45
        self.hashes=[]

    def read(self,url,body=None):
        """Keep all calls within one worker lease and retain exact source hashes."""
        remaining=self.deadline-time.monotonic()
        if remaining<=0:
            raise Invalid("Report read budget expired; narrow the request and retry")
        result=report_request(url,self.headers,body,timeout=min(15,remaining))
        self.hashes.append(digest(result))
        return result


def numeric_scope(binding,key):
    """Require a numeric provider identity; no input can become a URL path."""
    value=required(binding.get(key),key,30)
    if not value.isdigit():
        raise Invalid(key+" must be numeric")
    return value


def read_report(binding,app_id,options,connection_id=None,connection_version=None):
    """Dispatch a validated app-scoped read; results never authorize external writes."""
    report_options(binding.get("provider"),options)
    if binding.get('provider')=='google_play':
        return google_report(binding,app_id,options)
    store_id=numeric_scope(binding,"store_app_id")
    headers={"Authorization":"Bearer "+credential(binding,app_id)}
    if binding["provider"]=="apple_ads":
        headers["X-AP-Context"]="adAccountId="+numeric_scope(binding,"account_id")
    reader=Reader(headers)
    if options['operation'] in ('analytics_metrics','analytics_metrics_latest'):
        return prepare_analytics_metrics(reader,binding,app_id,store_id,options,
                                         connection_id,connection_version)
    if options["operation"]=="reviews":
        report=reviews(reader,store_id)
    elif options["operation"]=="subscription_catalog":
        report=read_catalog(reader,store_id)
    elif options["operation"]=="release_inventory":
        report=read_inventory(reader,store_id,options['version_id'])
    elif options["operation"]=="analytics_reports":
        report=read_analytics(reader,store_id)
    elif options["operation"]=="campaign_report":
        report=campaigns(reader,binding,options)
    else:
        verify_campaigns(reader,binding,options["campaign_ids"])
        report=read_keywords(reader,binding,options,query_body,report_pagination)
    return dict(report,provider=binding["provider"],app_id=app_id,store_app_id=store_id,
                observed_at=now(),source_hash=digest(reader.hashes),page_source_hashes=reader.hashes,
                request=options,external_writes=False,scope=("Catalog observation only; approval, prices, purchase and restore require separate verification" if options['operation']=='subscription_catalog' else "Provider observation only; installs do not prove paid or retained customers"))


def prepare_analytics_metrics(reader,binding,app_id,store_id,options,connection_id,connection_version):
    """Read one explicit complete downloads instance and prepare local partitions."""
    connection_id=analytics_identity(connection_id)
    if type(connection_version) is not int or not 1<=connection_version<=2147483647:
        raise Invalid('Apple analytics read requires the current connection version')
    inventory=read_analytics(reader,store_id)
    report=next((item for item in inventory['reports'] if item['id']==options['report_id']),None)
    if (inventory['coverage']!='COMPLETE' or report is None
            or report['coverage']!='COMPLETE'
            or report['name']!='App Downloads Standard'):
        raise Invalid('Choose a complete App Downloads Standard report from this app')
    if options['operation']=='analytics_metrics_latest':
        daily=[item for item in report['instances'] if item['granularity']=='DAILY']
        if not daily:
            raise Invalid('No complete daily downloads report instance is available yet')
        latest_date=max(item['processing_date'] for item in daily)
        newest=[item for item in daily if item['processing_date']==latest_date]
        if len(newest)!=1:
            raise Invalid('Apple returned ambiguous latest daily report instances')
        selected=newest[0]
    else:
        selected=next((item for item in report['instances'] if item['id']==options['instance_id']),None)
        if selected is None or selected['granularity']!='DAILY':
            raise Invalid('Choose a complete daily downloads report instance')
    selected_id=selected['id']
    segments=read_instance_segments(reader,store_id,options['report_id'],selected_id)
    key=dict(app_id=app_id,store_app_id=store_id,connection_id=connection_id,
        connection_version=connection_version,report_id=options['report_id'],
        report_family=report['name'],granularity=selected['granularity'])
    partitions=tuple(parse_partitions(key,selected['processing_date'],segments,True))
    public_binding={name:value for name,value in binding.items() if not name.startswith('_')}
    return PreparedAppleMetrics(identity=key,partitions=partitions,
        connection_hash=digest(public_binding),metadata_source_hash=digest(reader.hashes),
        operation=options['operation'])


def google_report(binding,app_id,options):
    """Read only a validated protected Google target, retaining typed source and coverage evidence."""
    from .play_contract import connection_metadata
    from .play_auth import PlayReader
    from .play_reports import read
    selected=connection_metadata(binding)
    reader=PlayReader(selected,credential(binding,app_id))
    report=read(selected,options['operation'],reader)
    return dict(report,app_id=app_id,store_app_id=selected['package_name'],request=options)


def review_record(row):
    """Project public review evidence while excluding reviewer nickname and links."""
    if not isinstance(row,dict) or row.get("type")!="customerReviews" or not isinstance(row.get("attributes"),dict):
        raise Invalid("Malformed customer review row")
    rid=required(row.get("id"),"Review ID",200)
    a=row["attributes"]
    if type(a.get("rating")) is not int or not 1<=a["rating"]<=5:
        raise Invalid("Review rating must be a whole number from 1 to 5")
    iso_time(a.get("createdDate"))
    return {"id":rid,"rating":a["rating"],"title":a.get("title"),"body":a.get("body"),
            "createdDate":a["createdDate"],"territory":a.get("territory"),"confirmed_incident":False}


def review_next(payload,path,seen):
    """Reject hostile or repeating pagination links before credentials reach them."""
    links=payload.get("links")
    if not isinstance(links,dict):
        raise Invalid("Review pagination coverage is missing")
    value=links.get("next")
    if value is None:
        return None
    if not isinstance(value,str):
        raise Invalid("Malformed review pagination")
    p=urlsplit(value)
    if p.scheme!="https" or p.netloc!="api.appstoreconnect.apple.com" or p.path!=path or p.fragment or value in seen:
        raise Invalid("Unsafe or repeating review pagination")
    return value


def reviews(reader,store_id):
    """Fetch bounded app reviews with duplicate conflict detection and clear coverage."""
    base="https://api.appstoreconnect.apple.com/v1/apps/"+store_id
    identity=reader.read(base)
    if str(identity.get("data",{}).get("id"))!=store_id:
        raise Invalid("Provider returned a different app identity")
    path="/v1/apps/"+store_id+"/customerReviews"
    url="https://api.appstoreconnect.apple.com"+path+"?"+urlencode({"limit":100,"sort":"-createdDate"})
    seen=set();rows={};pages=0
    for _ in range(3):
        seen.add(url)
        payload=reader.read(url);pages+=1
        source=payload.get("data")
        if not isinstance(source,list) or len(source)>100:
            raise Invalid("Review page shape exceeds its contract")
        for item in source:
            row=review_record(item)
            if row["id"] in rows and rows[row["id"]]!=row:
                raise Invalid("Conflicting duplicate customer review")
            rows[row["id"]]=row
        url=review_next(payload,path,seen)
        if not url:
            break
    return {"operation":"reviews","rows":list(rows.values()),"pages":pages,
            "coverage":"PARTIAL" if url else "COMPLETE","low_star_count":sum(r["rating"]<=2 for r in rows.values()),
            "interpretation":"Public complaints require investigation; no automatic confirmed P0 or clean baseline inferred"}


def query_body(options,offset):
    """Construct only the documented report query, never campaign creation or updates."""
    window={"start":options["start"],"end":options["end"],"timeZone":"ORTZ" if options["operation"]=="search_term_report" else "UTC"}
    if options["operation"] in REPORT_PATHS and options["start"]!=options["end"]:
        window["granularity"]="DAILY"
    return {"filters":[{"field":"campaignId","operator":"IN","value":options["campaign_ids"]}],
            "timeRange":window,
            "pagination":{"offset":offset,"pageSize":100,"fetchTotalCount":True}}


def verify_campaigns(reader,binding,ids):
    """Prove every requested campaign belongs to this app and exact ad account."""
    payload=reader.read("https://api.ads.apple.com/v1/campaigns/query",{
        "filters":[{"field":"id","operator":"IN","value":ids}],
        "pagination":{"offset":0,"pageSize":100,"fetchTotalCount":True}})
    source=payload.get("result")
    if not isinstance(source,list) or len(source)!=len(ids):
        raise Invalid("Requested campaign identities are missing or incomplete")
    actual=[]
    for c in source:
        if not isinstance(c,dict) or c.get("promotedObjectType")!="APPSTORE_APP" or str(c.get("promotedObjectId"))!=binding["store_app_id"] or str(c.get("adAccountId"))!=binding["account_id"]:
            raise Invalid("Campaign belongs to another app or ad account")
        actual.append(str(c.get("id")))
    if set(actual)!=set(ids):
        raise Invalid("Campaign identity response does not match the requested IDs")


def campaign_page(payload,binding,ids,offset):
    """Check row scope and exact pagination before accepting performance observations."""
    result=payload.get("result")
    if not isinstance(result,dict):
        raise Invalid("Unrecognized campaign report envelope")
    rows=result.get("rows",[])
    if not isinstance(rows,list) or len(rows)>100:
        raise Invalid("Campaign report page exceeds its contract")
    for row in rows:
        campaign_row(row,binding,ids)
    total=report_pagination(payload,offset,rows)
    return rows,total


def campaign_row(row,binding,ids):
    """Require scoped campaign metadata and preserve actually supplied metrics."""
    if not isinstance(row,dict) or not isinstance(row.get("metadata"),dict):
        raise Invalid("Campaign report metadata is missing")
    m=row["metadata"]
    identity=(m.get("promotedObjectType"),str(m.get("promotedObjectId")),str(m.get("adAccountId")))
    expected=("APPSTORE_APP",binding["store_app_id"],binding["account_id"])
    if str(m.get("id")) not in ids or identity!=expected:
        raise Invalid("Campaign report contains out-of-scope data")
    if not isinstance(row.get("totalMetrics"),dict):
        raise Invalid("Report metrics are missing")


def report_pagination(payload,offset,rows):
    """Reject incomplete or contradictory offset metadata before advancing a page."""
    p=payload.get("pagination",{})
    if any(type(p.get(k)) is not int for k in ("offset","pageSize","totalCount")) or p["offset"]!=offset or not 0<=p["pageSize"]<=100 or p["totalCount"]<offset+len(rows):
        raise Invalid("Campaign report pagination is invalid")
    if not rows and p["totalCount"]>offset:
        raise Invalid("Campaign report page is empty before its declared end")
    return p["totalCount"]


def campaigns(reader,binding,options):
    """Read current campaign metrics; retain nulls and never synthesize revenue."""
    verify_campaigns(reader,binding,options["campaign_ids"])
    rows=[];offset=0;total=None;pages=0
    for _ in range(3):
        payload=reader.read("https://api.ads.apple.com/v1/reports/apps/campaigns/query",query_body(options,offset));pages+=1
        page,total=campaign_page(payload,binding,options["campaign_ids"],offset)
        rows.extend(page);offset+=len(page)
        if offset>=total:
            break
    return {"operation":"campaign_report","api_version":"PLATFORM_V1","rows":rows,"pages":pages,
            "coverage":"COMPLETE" if offset>=total else "PARTIAL","declared_rows":total,
            "interpretation":"UTC report window; provider metrics may restate; missing fields remain unavailable"}
