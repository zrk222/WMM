"""Closed, finite inputs for an owner-reviewed campaign scope."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from .common import Invalid, digest, iso_time, required, safe_data
from .social_contract import reference

HASH = re.compile(r'[0-9a-f]{64}\Z')
NUMERIC = re.compile(r'[0-9]{1,40}\Z')
SCOPE_FIELDS = ('connection_id','page_id','ad_account_id','currency','expires_at','max_posts',
                'max_calls','max_campaigns','max_campaign_minor','max_total_minor',
                'approved_content_hashes','approved_rights_hashes','approved_targeting_hashes',
                'billing_acknowledged','ordinary_ad_attestation')
REEL_SCHEMA = 'wmm.facebook-page-reel.v1'
REEL_FIELDS = (
    'schema', 'request_id', 'app_id', 'page_id', 'policy_id', 'policy_hash',
    'admission_id', 'admission_hash', 'rights_hashes', 'artifact_id',
    'artifact_sha256', 'caption',
)


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise Invalid('Use the exact campaign fields shown in the owner review')


def numeric(value):
    if not isinstance(value, str) or not NUMERIC.fullmatch(value):
        raise Invalid('Use an exact numeric Meta account or Page ID')
    return value


def whole(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Invalid('Campaign limit is outside its finite supported range')
    return value


def hashes(value, required_list):
    if not isinstance(value,list) or len(value)>100 or (required_list and not value):
        raise Invalid('Provide the finite approved hash list')
    if any(not isinstance(item,str) or not HASH.fullmatch(item) for item in value):
        raise Invalid('Use lowercase SHA-256 hashes')
    if len(set(value)) != len(value):
        raise Invalid('Approved hashes must be distinct')
    return sorted(value)


def scope_acknowledgments(body,paid):
    if type(body['billing_acknowledged']) is not bool or (paid and not body['billing_acknowledged']):
        raise Invalid('Acknowledge billing uncertainty before paid scope review')
    if type(body['ordinary_ad_attestation']) is not bool or (paid and not body['ordinary_ad_attestation']):
        raise Invalid('Confirm the promotion is outside special ad categories before paid review')


def scope_limits(body):
    whole(body['max_posts'],0,100);whole(body['max_calls'],1,500)
    whole(body['max_campaigns'],0,20);whole(body['max_campaign_minor'],0,100000000)
    whole(body['max_total_minor'],0,100000000)
    if body['max_campaign_minor'] > body['max_total_minor']:
        raise Invalid('Per-campaign budget cannot exceed the total media commitment')
    paid=body['ad_account_id'] is not None
    limits=[body['max_campaigns'],body['max_campaign_minor'],body['max_total_minor']]
    if (paid and not all(limits)) or (not paid and any(limits)):
        raise Invalid('Select an ad account and positive bounded paid limits together')
    scope_acknowledgments(body,paid)
    return paid


def scope_data(body):
    exact(body,SCOPE_FIELDS); safe_data(body)
    reference(body['connection_id']);numeric(body['page_id'])
    if body['ad_account_id'] is not None:numeric(body['ad_account_id'])
    if not isinstance(body['currency'],str) or not re.fullmatch(r'[A-Z]{3}',body['currency']):
        raise Invalid('Use an explicit three-letter currency')
    expiry=iso_time(body['expires_at']); current=datetime.now(timezone.utc)
    if not current < expiry <= current+timedelta(hours=24):
        raise Invalid('Choose an expiry within the next 24 hours')
    paid=scope_limits(body)
    result=dict(body);result['expires_at']=expiry.isoformat()
    result['approved_content_hashes']=hashes(body['approved_content_hashes'],True)
    result['approved_rights_hashes']=hashes(body['approved_rights_hashes'],True)
    result['approved_targeting_hashes']=hashes(body['approved_targeting_hashes'],paid)
    return result


def post_data(body):
    exact(body,('request_id','message','link','content_hash','rights_hash'));safe_data(body)
    reference(body['request_id']);message=required(body['message'],'Post message',5000)
    link=body['link']
    if link is not None:
        if not isinstance(link,str) or len(link)>2048:raise Invalid('Use a bounded HTTPS link')
        parts=urlsplit(link)
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
            raise Invalid('Use a public HTTPS link without credentials')
    content_hash=digest(dict(message=message,link=link))
    if body['content_hash'] != content_hash:raise Invalid('Post content changed since review')
    hashes([body['rights_hash']],True)
    return dict(request_id=body['request_id'],message=message,link=link,
                content_hash=content_hash,rights_hash=body['rights_hash'])


def reel_data(body):
    """Validate an exact local Reel request before checking its durable authority."""
    from .operation_catalog import path_segment

    exact(body, REEL_FIELDS)
    if body['schema'] != REEL_SCHEMA:
        raise Invalid('Use the supported Facebook Page Reel request version')
    path_segment(body['app_id'])
    numeric(body['page_id'])
    for key in ('request_id', 'policy_id', 'admission_id', 'artifact_id'):
        reference(body[key])
    for key in ('policy_hash', 'admission_hash', 'artifact_sha256'):
        hashes([body[key]], True)
    rights = hashes(body['rights_hashes'], True)
    caption = body['caption']
    required(caption, 'Reel caption', 5000)
    if re.search(r'[\x00-\x09\x0b-\x1f\x7f\ud800-\udfff]', caption):
        raise Invalid('Use printable Unicode and line breaks in the Reel caption')
    safe_data(body)
    return dict(body, rights_hashes=rights)


def target_countries(body):
    target=body['targeting'];exact(target,('countries',))
    countries=target['countries']
    if not isinstance(countries,list) or not 1<=len(countries)<=20:
        raise Invalid('Choose one to twenty target countries')
    if any(not isinstance(x,str) or not re.fullmatch(r'[A-Z]{2}',x) for x in countries):
        raise Invalid('Target countries must use uppercase two-letter codes')
    if countries!=sorted(set(countries)):raise Invalid('Target countries must be unique and sorted')
    if digest(target)!=body['targeting_hash']:raise Invalid('Targeting changed since review')


def ad_data(body):
    """Validate one existing-Page-post promotion with a closed targeting surface."""
    exact(body,('request_id','post_id','content_hash','rights_hash','targeting_hash',
                'lifetime_budget_minor','end_time','targeting','name'))
    safe_data(body);reference(body['request_id'])
    if not isinstance(body['post_id'],str) or not re.fullmatch(r'[0-9]{1,40}_[0-9]{1,40}',body['post_id']):
        raise Invalid('Use the exact verified Facebook post ID')
    for key in ('content_hash','rights_hash','targeting_hash'):hashes([body[key]],True)
    whole(body['lifetime_budget_minor'],1,100000000)
    deadline=iso_time(body['end_time'])
    if deadline<=datetime.now(timezone.utc):raise Invalid('Campaign end must be in the future')
    target_countries(body)
    result=dict(body);result['end_time']=deadline.isoformat()
    result['name']=required(body['name'],'Campaign name',100)
    return result
