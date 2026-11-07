"""Per-owner, fresh-identity publication contexts; no credentials cross the API."""
import re
from .common import Invalid
from .social_connections import Connections
from .social_auth import app_secret_proof,validated_scopes
from .social_contract import display,opaque
from .social_profiles import verify
from .social_tokens import Grant
from .social_transport import request,metered_reads
from .publication_instagram_connection import assert_saved_connection
from .publication_transport import Context

_REQUIRED={'youtube':{'https://www.googleapis.com/auth/youtube.upload'},'tiktok':{'video.publish','video.list'},'linkedin':{'w_member_social'}}

def _load(store,app_id,connection_id,version):
    connections=Connections(store);row=connections.get(app_id,connection_id);connections.alive(row)
    if row['version']!=version:raise Invalid('Saved channel changed; reconnect and review')
    config=connections.setup.get(app_id,row['provider'])
    if config['version']!=row['config_version'] or config['status']=='DISCONNECTED':
        raise Invalid('Channel setup changed; reconnect and review')
    scopes=validated_scopes(config['data'])
    client=connections.secrets.load(app_id,row['provider'],config['secret_ref']) if config['secret_ref'] else {}
    credentials=connections.secrets.load(app_id,row['provider'],row['secret_ref'])
    return connections,row,config['data'],scopes,client.get('client_secret',''),credentials

def _bound(connections,row,heartbeat):
    def alive():
        heartbeat();connections.alive(row)
    return alive

def _instagram(connections,row,config,scopes,secret,credentials,expected,before_call,heartbeat):
    if row['provider']!='facebook':raise Invalid('Connect a Facebook Page linked to your Instagram professional account for local video upload')
    draft={'app_id':row['app_id'],'connection_id':row['id'],'connection_version':row['version'],'provider':'instagram','destination_id':expected}
    page=assert_saved_connection(row,draft)
    if not {'instagram_basic','instagram_content_publish'}.issubset(scopes):raise Invalid('Reconnect Facebook Page with Instagram publishing permissions')
    token=opaque(credentials.get('page_token'),'Page access token');proof=app_secret_proof(token,secret)
    alive=_bound(connections,row,heartbeat);alive()
    with metered_reads(before_call):
        raw=request('facebook','instagram_account',{'account':page,'appsecret_proof':proof},bearer=token,alive=alive)
    if not isinstance(raw,dict) or str(raw.get('id'))!=page or not isinstance(raw.get('instagram_business_account'),dict):raise Invalid('The selected Page has no verified Instagram professional account')
    ig=raw['instagram_business_account'];subject=ig.get('id')
    if not isinstance(subject,str) or not re.fullmatch(r'[0-9]{1,32}',subject) or subject!=expected:raise Invalid('Linked Instagram account changed; review the destination')
    return {'destination_id':subject,'name':display(ig.get('username')),'page_id':page,'connection_id':row['id'],'connection_version':row['version']},token

def _standard_identity(connections,row,config,scopes,secret,credentials,draft,before_call,heartbeat):
    """Reverify a non-Facebook channel and return only its destination token."""
    provider=draft['provider']
    required=_REQUIRED.get(provider)
    if required is None or row['provider']!=provider:raise Invalid('Publication channel connection changed')
    data=row['data'];facts=data.get('facts',{});identity=data.get('identity',{});destination=data.get('destination',{})
    if not required.issubset(scopes) or not isinstance(facts.get('reported_scopes'),list) or not required.issubset(facts['reported_scopes']) or not isinstance(identity.get('permissions'),list) or not required.issubset(identity['permissions']):raise Invalid('Reconnect and grant the channel publishing permissions')
    if destination.get('id')!=draft['destination_id']:raise Invalid('Publication destination changed')
    alive=_bound(connections,row,heartbeat);alive()
    with metered_reads(before_call):
        found=verify(config,secret,Grant(credentials,facts),alive=alive)
    if found.subject_id!=row['subject_id'] or not any(item.get('id')==draft['destination_id'] for item in found.destinations) or not isinstance(found.permissions,list) or not required.issubset(found.permissions):raise Invalid('Channel identity or publishing permissions changed')
    return opaque(credentials.get('access_token'),'channel access token')


def context(store,app_id,draft,before_call,heartbeat):
    """Load only the selected owner's current vault bundle and reverify one provider identity."""
    if not callable(before_call) or not callable(heartbeat) or draft.get('app_id')!=app_id:raise Invalid('Invalid publication authority context')
    connections,row,config,scopes,secret,credentials=_load(store,app_id,draft['connection_id'],draft['connection_version'])
    provider=draft['provider']
    if provider=='instagram':
        _,token=_instagram(connections,row,config,scopes,secret,credentials,draft['destination_id'],before_call,heartbeat)
        return Context(provider,draft['destination_id'],token,before_call,heartbeat,login_family='facebook')
    token=_standard_identity(connections,row,config,scopes,secret,credentials,draft,before_call,heartbeat)
    return Context(provider,draft['destination_id'],token,before_call,heartbeat)


def _instagram_page(row,scopes):
    """Require the saved Facebook Page and both locally observed Instagram scopes."""
    if row['provider']!='facebook':raise Invalid('Connect a Facebook Page linked to your Instagram professional account for local video upload')
    data=row['data'];destination=data.get('destination',{});identity=data.get('identity',{})
    if destination.get('kind')!='PAGE' or not {'instagram_basic','instagram_content_publish'}.issubset(identity.get('permissions') or []) or not {'instagram_basic','instagram_content_publish'}.issubset(scopes):raise Invalid('Reconnect Facebook Page with Instagram publishing permissions')
    page=destination.get('id')
    if not isinstance(page,str) or not re.fullmatch(r'[0-9]{1,32}',page):raise Invalid('Invalid selected Facebook Page')
    return page


def _read_instagram_link(connections,row,secret,credentials,page,heartbeat,before_call):
    """Read the Page's current Instagram link and return a secret-free binding."""
    token=opaque(credentials.get('page_token'),'Page access token');proof=app_secret_proof(token,secret);alive=_bound(connections,row,heartbeat)
    alive()
    with metered_reads(before_call):
        raw=request('facebook','instagram_account',{'account':page,'appsecret_proof':proof},bearer=token,alive=alive)
    if not isinstance(raw,dict) or str(raw.get('id'))!=page or not isinstance(raw.get('instagram_business_account'),dict):raise Invalid('The selected Page has no verified Instagram professional account')
    ig=raw['instagram_business_account'];subject=ig.get('id')
    if not isinstance(subject,str) or not re.fullmatch(r'[0-9]{1,32}',subject):raise Invalid('Instagram identity is invalid')
    return {'destination_id':subject,'name':display(ig.get('username')),'page_id':page,'connection_id':row['id'],'connection_version':row['version']}

def inspect_instagram(store,app_id,connection_id,version,before_call,heartbeat):
    """Resolve the current selected Page to its linked Instagram account, read-only."""
    if not callable(before_call) or not callable(heartbeat):raise Invalid('Invalid publication authority context')
    connections,row,config,scopes,secret,credentials=_load(store,app_id,connection_id,version)
    page=_instagram_page(row,scopes)
    return _read_instagram_link(connections,row,secret,credentials,page,heartbeat,before_call)
