"""Data-only compiled inspector projection; no mutation execution or authorization."""
import copy
import hashlib
import hmac
import json
import re
from pathlib import PurePosixPath,PureWindowsPath
from urllib.parse import urlsplit,unquote
from .common import Invalid,canonical,digest

MAX_JSON_BYTES=1048576
MAX_FIELDS=10000
MAX_OWNERS=1000
MAX_DEPTH=32
PUBLIC_FIELD=('label','domain','page','section','summary','control','value','schema',
              'options','unit','number','multiline','swatches')
CONTROLS={'text','number','boolean','select','color','list','record'}


def finite(value,depth=0):
    """Bound nesting before encoding untrusted JSON data."""
    if type(value) not in (dict,list,str,int,float,bool,type(None)):
        raise Invalid('Inspector accepts only JSON objects, arrays and primitive values')
    if depth>MAX_DEPTH:raise Invalid('Inspector JSON nesting exceeds its bound')
    if isinstance(value,dict):
        if any(type(k) is not str for k in value):raise Invalid('Inspector JSON keys must be strings')
        for item in value.values():finite(item,depth+1)
    elif isinstance(value,list):
        for item in value:finite(item,depth+1)
    try:encoded=canonical(value).encode('utf-8')
    except (ValueError,TypeError,RecursionError,UnicodeError):raise Invalid('Inspector needs finite JSON data') from None
    if len(encoded)>MAX_JSON_BYTES:raise Invalid('Inspector JSON exceeds its bound')
    return copy.deepcopy(value)


def public_data(value):
    """Public metadata cannot smuggle source endpoints or private absolute paths."""
    value=finite(value)
    public_strings(value)
    return value


def public_strings(value):
    if isinstance(value,str):
        public_text(value)
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('preimage','srcdoc','endpoint'):raise Invalid('Inspector public data contains private metadata')
            public_strings(key);public_strings(item)
    if isinstance(value,list):
        for item in value:public_strings(item)


def public_text(value):
    """Check embedded URLs separately from remaining prose/path tokens."""
    normalized=value.translate({9:None,10:None,13:None})
    if normalized!=value:
        public_text(normalized)
    urls=re.compile(r'https?://[^\s<>"\x00-\x20]+',re.I)
    for match in urls.finditer(value):public_url(match.group())
    prose=urls.sub(' PUBLIC_URL ',value)
    if re.search(r'(?<![A-Za-z0-9])/(?:[^\s/]|/)|\\\\[^\s\\]+\\',prose):
        raise Invalid('Inspector public data contains a private path')
    for token in re.split(r'[\s<>"\x00-\x20]+',prose):
        token=token.lstrip("([{'")
        if token=='/':continue
        if PureWindowsPath(token).is_absolute() or PurePosixPath(token).is_absolute() or token.lower().startswith('file:'):
            raise Invalid('Inspector public data contains a private path')
    if re.search(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]',prose):
        raise Invalid('Inspector public data contains a private path')


def public_url(value):
    try:
        parsed=urlsplit(value)
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise Invalid('Inspector public URL contains credentials or lacks a host')
        if '\\' in value or unquote(parsed.netloc)!=parsed.netloc:
            raise Invalid('Inspector public URL authority is unsupported')
        parsed.port
    except ValueError as error:
        raise Invalid('Inspector public URL is invalid') from error


def metadata(value,allowed):
    if not isinstance(value,dict) or not set(value)<=set(allowed):
        raise Invalid('Inspector metadata contains unsupported private fields')


def typed_metadata(value,types):
    metadata(value,types)
    for key,item in value.items():
        expected=types[key]
        if expected=='number':valid=type(item) in (int,float)
        elif expected=='strings':valid=isinstance(item,list) and all(isinstance(v,str) for v in item)
        else:valid=type(item) is expected
        if not valid:raise Invalid('Inspector metadata value has an unsupported type')


def public_schema(value):
    """Preserve the exact public ValueSchema vocabulary, never source metadata."""
    vocabulary={'null':(), 'boolean':(), 'number':('integer','minimum','maximum'),
        'string':('enum','minLength','maxLength','format'),'literal':('value',),
        'array':('items','minItems','maxItems'),'object':('fields','allowUnknown'),
        'oneOf':('variants',),'blob':('mediaTypes','maxBytes')}
    if not isinstance(value,dict) or not isinstance(value.get('kind'),str) or value['kind'] not in vocabulary:
        raise Invalid('Inspector public schema kind is unsupported')
    metadata(value,('kind',*vocabulary[value['kind']]))
    schema_scalars(value)
    nested_schema(value)
    return value


def schema_scalars(value):
    rules={'kind':str,'integer':bool,'minimum':'number','maximum':'number','enum':'strings',
        'minLength':int,'maxLength':int,'format':str,'minItems':int,'maxItems':int,
        'allowUnknown':bool,'mediaTypes':'strings','maxBytes':int}
    typed_metadata({k:v for k,v in value.items() if k in rules},rules)


def nested_schema(value):
    kind=value['kind']
    if kind=='array':public_schema(value.get('items'))
    if kind=='oneOf':
        if not isinstance(value.get('variants'),list):raise Invalid('Inspector schema variants are invalid')
        for variant in value['variants']:public_schema(variant)
    if kind=='object':
        if not isinstance(value.get('fields'),dict):raise Invalid('Inspector schema fields are invalid')
        for field in value['fields'].values():
            metadata(field,('schema','optional'))
            if 'optional' in field and type(field['optional']) is not bool:raise Invalid('Inspector schema optional flag is invalid')
            public_schema(field.get('schema'))


def public_field(field):
    value=public_data({k:field[k] for k in PUBLIC_FIELD if k in field})
    typed_metadata({k:v for k,v in value.items() if k in ('label','domain','summary','control','unit','multiline','swatches')},
                   dict(label=str,domain=str,summary=str,control=str,unit=str,multiline=bool,swatches='strings'))
    if 'schema' in value:public_schema(value['schema'])
    for name in ('page','section'):
        if name in value:typed_metadata(value[name],dict(id=str,label=str))
    if 'number' in value:typed_metadata(value['number'],dict(scale='number',suffixes='strings',minimum='number',maximum='number',step='number'))
    if 'options' in value:public_options(value['options'])
    return value


def public_options(options):
    if not isinstance(options,list):raise Invalid('Inspector options must be a list')
    for option in options:
        if isinstance(option,str):continue
        metadata(option,('value','label','description','preview'))
        typed_metadata({k:v for k,v in option.items() if k in ('label','description')},dict(label=str,description=str))
        if type(option.get('value')) not in (str,int,float,bool):raise Invalid('Inspector option value is invalid')
        if 'preview' in option:
            preview=option['preview']
            if not isinstance(preview,dict):raise Invalid('Inspector option preview is invalid')
            if not isinstance(preview.get('kind'),str):raise Invalid('Inspector option preview kind is invalid')
            fields={'color':('kind','color'),'font':('kind','family','sample')}.get(preview.get('kind'))
            if fields is None:raise Invalid('Inspector option preview kind is unsupported')
            metadata(preview,fields)
            typed_metadata(preview,{k:str for k in fields})


def proposal_value(field,value):
    """Primitive validation only; upstream remains the complex-schema authority."""
    value=finite(value);control=field['control']
    valid={'text':isinstance(value,str),'color':isinstance(value,str),
           'number':type(value) in (int,float),'boolean':type(value) is bool,
           'list':isinstance(value,list),'record':isinstance(value,dict),'select':True}
    if not valid.get(control,False):raise Invalid('Inspector proposal type does not match its compiled control')
    options=field.get('options')
    if options is not None:
        allowed=[v.get('value') if isinstance(v,dict) else v for v in options]
        if not any(canonical(value)==canonical(v) for v in allowed):
            raise Invalid('Inspector proposal is outside the compiled choices')
    return value


class ControlView:
    """A broker-local immutable view; refresh it from the live session before use."""
    def __init__(self,scope,snapshot,key):
        if not isinstance(key,bytes) or len(key)<32:raise Invalid('Inspector needs a private session identity key')
        if not isinstance(scope,dict) or set(scope)!={'app_id','session_id'}:
            raise Invalid('Inspector needs exact app and session scope')
        if any(not isinstance(v,str) or not v or len(v)>100 for v in scope.values()):
            raise Invalid('Inspector app and session identities are invalid')
        if not isinstance(snapshot,dict):raise Invalid('Inspector snapshot must be an object')
        self.scope=public_data(scope);self.snapshot=finite(snapshot);self.key=key
        self.revision=self.snapshot.get('revision');self.owners={};self.fields={}
        if type(self.revision) is not int or self.revision<1:raise Invalid('Inspector revision is invalid')
        self.view=dict(scope=self.scope,revision=self.revision,owners=[],
                       execution='NOT_RUN_PROPOSAL_ONLY',upstream_validation='REQUIRED',approval='NOT_ESTABLISHED')
        self.inventory()
        self.view['snapshot_hash']=digest(self.snapshot)
        self.view['view_hash']=digest(self.view)

    def opaque(self,kind,native):
        return hmac.new(self.key,canonical([self.scope,kind,native]).encode(),hashlib.sha256).hexdigest()

    def inventory(self):
        tracks=self.snapshot.get('tracks')
        if not isinstance(tracks,list):raise Invalid('Inspector tracks are missing')
        for track in tracks:
            self.track(track)

    def track(self,track):
        if not isinstance(track,dict) or not isinstance(track.get('id'),str):raise Invalid('Inspector track identity is invalid')
        if not isinstance(track.get('items',[]),list) or not isinstance(track.get('inspectorObjects',[]),list):
            raise Invalid('Inspector item collections must be lists')
        for item in track.get('items',[]):
            owner_item(item)
            self.owner(dict(kind='item',itemId=item['id']),item)
        for item in track.get('inspectorObjects',[]):
            owner_item(item)
            self.owner(dict(kind='track-object',trackId=track['id'],objectId=item['id']),item)

    def owner(self,native,item):
        if len(self.owners)>=MAX_OWNERS:raise Invalid('Inspector owner count exceeds its bound')
        identity=self.opaque('owner',native)
        if identity in self.owners:raise Invalid('Inspector has duplicate owner identities')
        self.owners[identity]=copy.deepcopy(native)
        fields=item.get('inspector',[])
        if not isinstance(fields,list):raise Invalid('Inspector fields must be a list')
        row=dict(id=identity,kind=native['kind'],fields=[])
        for field in fields:row['fields'].append(self.field(identity,field))
        self.view['owners'].append(row)

    def field(self,owner,field):
        if len(self.fields)>=MAX_FIELDS:raise Invalid('Inspector field count exceeds its bound')
        if not isinstance(field,dict) or not isinstance(field.get('id'),str) or not isinstance(field.get('control'),str) or field['control'] not in CONTROLS:
            raise Invalid('Inspector field identity or control is unsupported')
        identity=self.opaque('field',[owner,field['id']])
        if identity in self.fields:raise Invalid('Inspector has duplicate fields for one owner')
        public=public_field(field)
        public.update(id=identity,writable=isinstance(field.get('edit'),dict))
        self.fields[identity]=dict(owner=owner,native=copy.deepcopy(field),public=public)
        return public

    def public(self):
        return copy.deepcopy(self.view)

    def parameter(self,body):
        """Resolve only a current field; returned native envelope must stay private."""
        required={'revision','view_hash','owner_id','field_id','value'}
        if not isinstance(body,dict) or set(body)!=required:raise Invalid('Use only the compiled parameter proposal fields')
        if type(body['revision']) is not int or body['revision']!=self.revision or body['view_hash']!=self.view['view_hash']:
            raise Invalid('Inspector view changed; reload before editing')
        field=self.fields.get(body['field_id']) if isinstance(body['field_id'],str) else None
        if field is None or field['owner']!=body['owner_id']:raise Invalid('Inspector parameter does not belong to this owner')
        if not field['public']['writable']:raise Invalid('Inspector parameter is derived and read only')
        value=proposal_value(field['native'],body['value'])
        return dict(type='parameter.adjust',revision=self.revision,owner=copy.deepcopy(self.owners[field['owner']]),
                    parameterId=field['native']['id'],value=value)


def owner_item(value):
    if not isinstance(value,dict) or not isinstance(value.get('id'),str) or not value['id']:
        raise Invalid('Inspector owner identity is invalid')
