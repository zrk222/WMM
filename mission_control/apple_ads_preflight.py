"""Pure current Apple Ads inventory requests and strict app/account-bound pages."""
import re
from .common import Invalid, required

ENDPOINT="https://api.ads.apple.com/v1/campaigns/query"


def numeric_id(value,label):
    """Accept documented decimal identifiers, never booleans or URL syntax."""
    if type(value) is int:
        value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r"[0-9]{1,30}",value):
        raise Invalid(label+" must be a numeric identifier of at most 30 digits")
    return value


def inventory_request(binding):
    """Use declared app/ad-account scope before any credential is resolved."""
    store=numeric_id(required(binding.get("store_app_id"),"App Store ID",30),"App Store ID")
    account=numeric_id(required(binding.get("account_id"),"Apple Ads ad account ID",30),"Apple Ads ad account ID")
    body={"filters":[{"field":"promotedObjectType","operator":"EQUALS","value":"APPSTORE_APP"},
                     {"field":"promotedObjectId","operator":"EQUALS","value":store}],
          "pagination":{"offset":0,"pageSize":100,"fetchTotalCount":True}}
    return store,account,body


def campaign_identity(row,store,account):
    """Reject another app/account instead of preserving its private campaign data."""
    if not isinstance(row,dict):
        raise Invalid("Apple Ads returned a malformed campaign")
    if row.get("promotedObjectType")!="APPSTORE_APP" or str(row.get("promotedObjectId"))!=store or str(row.get("adAccountId"))!=account:
        raise Invalid("Apple Ads returned a campaign outside the selected app or ad account")
    return numeric_id(row.get("id"),"Campaign ID")


def pagination_numbers(value):
    """Require explicit nonnegative integer pagination, including an empty page."""
    if not isinstance(value,dict):
        raise Invalid("Apple Ads campaign pagination is missing")
    for key in ("offset","pageSize","totalCount"):
        if type(value.get(key)) is not int or value[key]<0:
            raise Invalid("Apple Ads campaign pagination is malformed")
    return {key:value[key] for key in ("offset","pageSize","totalCount")}


def validate_page(page,count):
    """A first bounded page cannot contradict its returned rows or declared total."""
    if page["offset"]!=0 or page["pageSize"]>100 or count>page["pageSize"] or page["totalCount"]<count:
        raise Invalid("Apple Ads campaign pagination contradicts the requested page")
    if count==0 and page["totalCount"]>0:
        raise Invalid("Apple Ads returned an empty page before its declared end")


def shape_inventory(payload,store,account):
    """Project one validated page; empty/partial inventory never proves app success."""
    if not isinstance(payload,dict) or not isinstance(payload.get("result"),list) or len(payload["result"])>100:
        raise Invalid("Apple Ads campaign response exceeds its current page contract")
    rows=payload["result"]
    ids=[campaign_identity(row,store,account) for row in rows]
    if len(set(ids))!=len(ids):
        raise Invalid("Apple Ads returned duplicate campaign identities")
    page=pagination_numbers(payload.get("pagination"))
    validate_page(page,len(rows))
    return {"data":rows,"campaign_ids":ids,"pagination":page,
            "coverage":"PARTIAL" if page["totalCount"]>len(rows) else "COMPLETE",
            "returned_count":len(rows),"total_count":page["totalCount"],
            "identity_proof":"RETURNED_CAMPAIGNS_MATCH_APP_AND_ACCOUNT" if rows else "NO_CAMPAIGN_IDENTITY_PROOF"}
