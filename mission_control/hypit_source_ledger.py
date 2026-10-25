"""Private source history and durable intent; never a runtime or approval grant."""
import hashlib
import json
from pathlib import PurePosixPath
import re
from .common import Invalid,canonical,digest,identifier,now,required,uid
from .db import connection
from .hypit_control_view import finite

MAX_FILES=32
MAX_SOURCE_BYTES=1048576
MAX_VERSIONS=200
MAX_ATTEMPTS=500


def source_bundle(value):
    """Freeze a finite Run/Author closure and exact UTF8 source bytes."""
    if type(value) is not dict or set(value)!={'upstream_revision','root','files'}:
        raise Invalid('Source observation needs upstream revision, Author root and files')
    value=dict(value)
    if type(value['upstream_revision']) is not int or value['upstream_revision']<1:
        raise Invalid('Source observation revision is invalid')
    files=value['files']
    if type(files) is not dict or not 1<=len(files)<=MAX_FILES:
        raise Invalid('Source closure count is invalid')
    files=dict(files);value['files']=files
    if not isinstance(value['root'],str) or 'build.svrun' not in files or value['root'] not in files:
        raise Invalid('Source closure needs its Run and Author root')
    if PurePosixPath(value['root']).suffix not in ('.svml','.svs'):
        raise Invalid('Author root must identify an SVML or SVS source')
    hashes={}
    for name,text in files.items():
        source_file(name,text)
        try:hashes[name]=hashlib.sha256(text.encode('utf-8')).hexdigest()
        except UnicodeError:raise Invalid('Source text must be valid UTF8') from None
    if sum(len(v.encode()) for v in files.values())>MAX_SOURCE_BYTES:
        raise Invalid('Source closure exceeds its byte bound')
    return dict(value,source_hashes=hashes,content_hash=digest(dict(root=value['root'],files=files)))


def source_file(name,text):
    if type(name) is not str or type(text) is not str:raise Invalid('Source names and content must be strings')
    try:name.encode('utf-8')
    except UnicodeError:raise Invalid('Source filename must be valid UTF8') from None
    path=PurePosixPath(name)
    if not name or ':' in name or '\\' in name or path.is_absolute() or path.as_posix()!=name or '..' in path.parts:
        raise Invalid('Source file must be a canonical project-relative path')
    if path.suffix not in ('.svml','.svs','.svrun') or not isinstance(text,str):
        raise Invalid('Only Run and Author text belongs in source history')


def checked(row):
    if row is None:raise Invalid('Studio history does not belong to this app and project')
    value=dict(row)
    try:data=json.loads(value['data'])
    except (ValueError,TypeError):raise Invalid('Studio saved history is unreadable') from None
    expected=attempt_hash(dict(value,data=data))
    if expected!=value['hash']:raise Invalid('Studio saved history changed; inspect before editing')
    value['data']=data
    return value


def attempt_hash(row):
    """Bind all saved row metadata and data, excluding only the checksum."""
    return digest({key:value for key,value in row.items() if key!='hash'})


def update_attempt(db,row,status,result_version):
    value=dict(row,status=status,result_version=result_version,updated=now())
    value['hash']=attempt_hash(value)
    db.execute('UPDATE studio_edit_attempts SET status=?,result_version=?,updated=?,hash=? WHERE app_id=? AND project_id=? AND id=?',
        (status,result_version,value['updated'],value['hash'],row['app_id'],row['project_id'],row['id']))
    return value


def history_current(db,app_id,project_id):
    """Validate bounded retained history before any new edit transition."""
    versions={};attempts=[]
    for table in ('studio_source_versions','studio_edit_attempts'):
        rows=db.execute('SELECT * FROM '+table+' WHERE app_id=? AND project_id=?',(app_id,project_id)).fetchall()
        maximum=MAX_VERSIONS if table=='studio_source_versions' else MAX_ATTEMPTS
        if len(rows)>maximum:raise Invalid('Studio retained history exceeds its bound')
        for row in rows:
            value=checked(row)
            if table=='studio_source_versions':versions[value['version']]=value
            else:attempts.append(value)
    if not versions or set(versions)!=set(range(1,len(versions)+1)):
        raise Invalid('Studio source history is not contiguous')
    head=current(db,app_id,project_id)
    if head['version']!=max(versions):raise Invalid('Studio source head differs from latest retained history')
    for row in attempts:attempt_link(row,versions)


def attempt_link(row,versions):
    base=row['data']['base_version']
    if base not in versions or row['data']['base_hash']!=versions[base]['hash']:
        raise Invalid('Studio intent base linkage changed')
    completed=row['status'] in ('APPLIED','REJECTED')
    if not completed:
        if row['result_version'] is not None:raise Invalid('Unresolved intent has a result version')
        return
    if row['result_version']!=base+1 or row['result_version'] not in versions:
        raise Invalid('Studio edit result linkage changed')
    if row['status']=='REJECTED' and versions[base]['data']['content_hash']!=versions[base+1]['data']['content_hash']:
        raise Invalid('Rejected edit source history changed')


def current(db,app_id,project_id):
    return checked(db.execute('SELECT v.* FROM studio_source_versions v JOIN studio_source_heads h ON h.app_id=v.app_id AND h.project_id=v.project_id AND h.version=v.version WHERE v.app_id=? AND v.project_id=?',
                              (app_id,project_id)).fetchone())


def receipt(row):
    value={k:row[k] for k in ('app_id','project_id','version','hash','created')}
    data=row['data'];value.update(upstream_revision=data['upstream_revision'],content_hash=data['content_hash'],
                                  source_hashes=data['source_hashes'],execution='NOT_AUTHORIZED_BY_LEDGER')
    return value


def attempt_receipt(row,dispatch=False):
    return dict(id=row['id'],status=row['status'],intent_hash=row['hash'],
        base_version=row['data']['base_version'],result_version=row['result_version'],
        dispatch_allowed=dispatch,authority='FRESH_BROKER_APPROVAL_REQUIRED')


def append(db,app_id,project_id,version,data):
    if version>MAX_VERSIONS:raise Invalid('Source history version limit reached')
    stamp=now()
    value=dict(app_id=app_id,project_id=project_id,version=version,data=data,created=stamp)
    db.execute('INSERT INTO studio_source_versions VALUES(?,?,?,?,?,?)',
               (app_id,project_id,version,canonical(data),attempt_hash(value),stamp))
    db.execute('INSERT INTO studio_source_heads VALUES(?,?,?) ON CONFLICT(app_id,project_id) DO UPDATE SET version=excluded.version',
               (app_id,project_id,version))
    return current(db,app_id,project_id)


class SourceLedger:
    def __init__(self,store):self.store=store

    def scope(self,app_id,project_id):
        self.store.app(app_id);identifier(project_id)

    def initialize(self,app_id,project_id,bundle):
        self.scope(app_id,project_id);data=source_bundle(bundle)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            exists=db.execute('SELECT 1 FROM studio_source_heads WHERE app_id=? AND project_id=?',(app_id,project_id)).fetchone()
            if exists:
                history_current(db,app_id,project_id)
                row=current(db,app_id,project_id)
                if row['data']!=data:raise Invalid('Studio project already has a different source head')
                return receipt(row)
            return receipt(append(db,app_id,project_id,1,data))

    def read(self,app_id,project_id):
        self.scope(app_id,project_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            history_current(db,app_id,project_id)
            head=current(db,app_id,project_id)
            versions=[receipt(checked(row)) for row in db.execute('SELECT * FROM studio_source_versions WHERE app_id=? AND project_id=? ORDER BY version',(app_id,project_id))]
            attempts=[attempt_receipt(checked(row)) for row in db.execute('SELECT * FROM studio_edit_attempts WHERE app_id=? AND project_id=? ORDER BY created,id',(app_id,project_id))]
            return dict(head=receipt(head),versions=versions,attempts=attempts)

    def prepare(self,app_id,project_id,body):
        self.scope(app_id,project_id)
        body=intent(body)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            head=current(db,app_id,project_id)
            history_current(db,app_id,project_id)
            old=db.execute('SELECT * FROM studio_edit_attempts WHERE app_id=? AND project_id=? AND request_key=?',(app_id,project_id,body['request_key'])).fetchone()
            if old:
                row=checked(old)
                if row['data']!=body:raise Invalid('Edit retry key belongs to different frozen inputs')
                return attempt_receipt(row)
            prepare_current(db,app_id,project_id,head,body)
            key=uid();stamp=now()
            value=dict(app_id=app_id,project_id=project_id,id=key,request_key=body['request_key'],data=body,
                       status='PREPARED',result_version=None,created=stamp,updated=stamp)
            db.execute('INSERT INTO studio_edit_attempts VALUES(?,?,?,?,?,?,?,?,?,?)',
                (app_id,project_id,key,body['request_key'],canonical(body),attempt_hash(value),'PREPARED',None,stamp,stamp))
            row=checked(db.execute('SELECT * FROM studio_edit_attempts WHERE app_id=? AND project_id=? AND id=?',(app_id,project_id,key)).fetchone())
            return attempt_receipt(row,True)

    def uncertain(self,app_id,project_id,attempt_id):
        self.scope(app_id,project_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');row=edit_attempt(db,app_id,project_id,attempt_id)
            history_current(db,app_id,project_id)
            if row['status'] not in ('PREPARED','UNCERTAIN'):raise Invalid('Completed edit cannot become uncertain')
            return attempt_receipt(update_attempt(db,row,'UNCERTAIN',None))

    def finish(self,app_id,project_id,attempt_id,outcome,bundle):
        self.scope(app_id,project_id);data=source_bundle(bundle)
        if outcome not in ('APPLIED','REJECTED'):raise Invalid('Use an observed accepted or rejected source outcome')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');row=edit_attempt(db,app_id,project_id,attempt_id)
            history_current(db,app_id,project_id)
            if row['status'] not in ('PREPARED','UNCERTAIN'):raise Invalid('Edit outcome already recorded; inspect its saved version')
            head=current(db,app_id,project_id);result_current(head,row,data,outcome)
            version=head['version']+1;append(db,app_id,project_id,version,data)
            return attempt_receipt(update_attempt(db,row,outcome,version))


def edit_attempt(db,app_id,project_id,attempt_id):
    return checked(db.execute('SELECT * FROM studio_edit_attempts WHERE app_id=? AND project_id=? AND id=?',(app_id,project_id,attempt_id)).fetchone())


def intent(body):
    body=finite(body)
    fields={'request_key','base_version','base_hash','view_hash','proposal_hash','actor'}
    if not isinstance(body,dict) or set(body)!=fields:raise Invalid('Edit intent fields are invalid')
    if type(body['base_version']) is not int or body['base_version']<1:raise Invalid('Edit base version is invalid')
    required(body['request_key'],'Request key',100);required(body['actor'],'Admitted actor',100)
    for name in ('base_hash','view_hash','proposal_hash'):
        if not isinstance(body[name],str) or not re.fullmatch('[a-f0-9]{64}',body[name]):raise Invalid('Edit intent hash is invalid')
    return body


def prepare_current(db,app_id,project_id,head,body):
    if head['version']>=MAX_VERSIONS:raise Invalid('Source history capacity is exhausted; do not dispatch an edit')
    if head['version']!=body['base_version'] or head['hash']!=body['base_hash']:raise Invalid('Source head changed; inspect before preparing an edit')
    rows=db.execute('SELECT status FROM studio_edit_attempts WHERE app_id=? AND project_id=?',(app_id,project_id)).fetchall()
    if len(rows)>=MAX_ATTEMPTS:raise Invalid('Edit attempt limit reached')
    if any(r['status'] in ('PREPARED','UNCERTAIN') for r in rows):raise Invalid('Unresolved edit requires inspection before another intent')


def result_current(head,row,data,outcome):
    if head['version']!=row['data']['base_version'] or head['hash']!=row['data']['base_hash']:raise Invalid('Source head changed during edit')
    previous=head['data']
    if set(data['files'])!=set(previous['files']) or data['root']!=previous['root']:raise Invalid('Edit changed the approved source closure')
    if data['upstream_revision']<previous['upstream_revision']:raise Invalid('Observed upstream revision moved backwards')
    changed=data['content_hash']!=previous['content_hash']
    if outcome=='REJECTED' and changed:raise Invalid('Rejected edit did not restore its previous source bytes')
    if changed and data['upstream_revision']<=previous['upstream_revision']:raise Invalid('Changed sources need a newer upstream revision')
