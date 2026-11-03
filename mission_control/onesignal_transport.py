"""Closed, pinned OneSignal setup transport. It cannot send messages or change billing."""
import json
import base64
import binascii
import re
import time
import uuid
from .common import Invalid, canonical, required
from .aeo_transport import PinnedHTTPS, address, response_body, response_headers
from .aeo_tls import trust_context
from .payment_signature import bounded_tree, unique_pairs

HOST='api.onesignal.com'
MAX_BODY=1048576
CHANNEL_FIELDS=frozenset(('apns_p8','apns_key_id','apns_team_id','apns_bundle_id','apns_env','fcm_v1_service_account_json'))
SAFE_FIELDS=('id','name','organization_id','apns_key_id','apns_team_id','apns_bundle_id','apns_env')
PRIVATE_RESPONSE_FIELDS=frozenset(('apns_p8','apns_p12','apns_p12_password','apns_certificates',
    'fcm_v1_service_account_json','gcm_key','chrome_key','safari_apns_certificate',
    'safari_apns_p12','safari_apns_p12_password','rest_api_key','basic_auth_key','api_key'))


def uuid_text(value):
    try:
        if not isinstance(value,str) or str(uuid.UUID(value))!=value:raise ValueError()
    except (TypeError,ValueError,AttributeError):raise Invalid('Use the exact OneSignal UUID') from None
    return value


def key_text(value):
    if not isinstance(value,str) or not re.fullmatch(r'[!-~]{16,1800}',value):
        raise Invalid('Enter the appropriate protected OneSignal API key')
    return value


def safe_app(value):
    """Project safe metadata immediately; provider responses may contain credentials."""
    if not isinstance(value,dict):raise Invalid('OneSignal returned an invalid app record')
    result={field:value[field] for field in SAFE_FIELDS if field in value}
    result['id']=uuid_text(result.get('id'))
    result['name']=required(result.get('name'),'OneSignal app name',128)
    if 'organization_id' in result and result['organization_id'] is not None:result['organization_id']=uuid_text(result['organization_id'])
    for field in SAFE_FIELDS[3:]:
        if field in result and result[field] is not None and (not isinstance(result[field],str) or len(result[field])>255):
            raise Invalid('OneSignal returned invalid platform metadata')
    return result


def parse(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BODY:raise Invalid('OneSignal returned an invalid bounded response')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_pairs);bounded_tree(value)
    except (ValueError,UnicodeError,RecursionError,Invalid):raise Invalid('OneSignal returned invalid JSON') from None
    return value


def private_variants(value):
    """Capture raw and encoded credential forms without returning or logging them."""
    if value is None or value=='':return set()
    if not isinstance(value,str):raise Invalid('OneSignal returned invalid private metadata')
    variants={value,base64.b64encode(value.encode('utf-8')).decode('ascii')}
    try:
        decoded=base64.b64decode(value,validate=True).decode('utf-8')
        if decoded:variants.add(decoded)
    except (ValueError,UnicodeError,binascii.Error):pass
    for text in tuple(variants):
        try:
            document=json.loads(text,object_pairs_hook=unique_pairs)
            if isinstance(document,dict):
                for field in ('private_key','private_key_id','client_email','client_id'):
                    item=document.get(field)
                    if isinstance(item,str) and item:
                        variants.add(item);variants.add(base64.b64encode(item.encode('utf-8')).decode('ascii'))
        except Invalid:raise Invalid('OneSignal returned invalid private metadata') from None
        except (ValueError,RecursionError):pass
    return variants


def payload(action,value):
    if action in ('list','view'):
        if value is not None:raise Invalid('Read-only setup does not accept a request body')
        return None
    if not isinstance(value,dict):raise Invalid('Use a bounded OneSignal setup body')
    if action=='create':
        if set(value)!={'name','organization_id'}:raise Invalid('Create accepts only name and organization')
        return {'name':required(value['name'],'OneSignal app name',128),'organization_id':uuid_text(value['organization_id'])}
    if action=='update':
        if not value or set(value)-CHANNEL_FIELDS:raise Invalid('Choose only supported push configuration fields')
        if any(not isinstance(v,str) or not v or len(v)>16384 or '\x00' in v for v in value.values()):
            raise Invalid('OneSignal channel configuration is invalid or too large')
        if 'apns_env' in value and value['apns_env'] not in ('production','development'):
            raise Invalid('Choose the APNs environment')
        for field in ('apns_p8','fcm_v1_service_account_json'):
            if field in value:
                try:base64.b64decode(value[field],validate=True).decode('utf-8')
                except (ValueError,UnicodeError,binascii.Error):raise Invalid('OneSignal private channel credentials must be valid base64') from None
        return dict(value)
    raise Invalid('Unsupported OneSignal setup operation')


def request(action,key,app_id=None,fields=None,alive=lambda:None):
    """One request, no redirects or automatic retry. No provider body escapes projection."""
    if action not in ('list','view','create','update'):raise Invalid('Unsupported OneSignal setup operation')
    key=key_text(key)
    if action in ('view','update'):path='/apps/'+uuid_text(app_id)
    else:
        if app_id is not None:raise Invalid('This operation does not take an app ID')
        path='/apps'
    method={'list':'GET','view':'GET','create':'POST','update':'PUT'}[action]
    data=payload(action,fields)
    raw_body=canonical(data).encode('utf-8') if data is not None else None
    if raw_body is not None and len(raw_body)>65536:raise Invalid('OneSignal setup body is too large')
    headers={'Authorization':'Key '+key,'Accept':'application/json','Accept-Encoding':'identity','Content-Type':'application/json'}
    deadline=time.monotonic()+30;alive();conn=None
    try:
        conn=PinnedHTTPS(HOST,address(HOST,deadline),trust_context(),deadline)
        conn.request(method,path,body=raw_body,headers=headers)
        response=conn.getresponse()
        if not 200<=response.status<300:raise Invalid('OneSignal did not confirm setup; inspect the provider before any new approval')
        result=parse(response_body(response,response_headers(response),MAX_BODY,conn,deadline))
        rows=result if isinstance(result,list) else [result]
        if action=='list' and (not isinstance(result,list) or len(result)>1000):
            raise Invalid('OneSignal app list is unavailable or too large')
        protected={key}
        if data:
            for field in ('apns_p8','fcm_v1_service_account_json'):
                if field in data:
                    protected.update(private_variants(data[field]))
        for item in rows:
            if isinstance(item,dict):
                for field in PRIVATE_RESPONSE_FIELDS:
                    if field in item:protected.update(private_variants(item[field]))
        if any(secret in item[field] for item in rows if isinstance(item,dict) for field in SAFE_FIELDS
               if isinstance(item.get(field),str) for secret in protected):
            raise Invalid('OneSignal returned protected data in metadata; response rejected')
        if action=='list':
            projected=[safe_app(item) for item in result]
            if len({item['id'] for item in projected})!=len(projected):raise Invalid('OneSignal app list contains ambiguous identities')
        else:projected=safe_app(result)
    except Invalid:raise
    except Exception:raise Invalid('OneSignal setup could not be confirmed; inspect the provider before another approval') from None
    finally:
        if conn is not None:conn.close()
    alive();return projected
