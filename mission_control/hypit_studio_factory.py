"""Frozen app-owned Studio source preparation; never launches native work."""
import hashlib
import json
import os
from pathlib import Path
from .common import Invalid,digest,identifier
from .db import connection
from .hypit_authoring import project
from .hypit_jobs import current_inputs
from .hypit_installation import discover,revalidate,plain,public_summary
from .hypit_studio_registry import Registry
from .hypit_studio_process import StudioProcess
from .hypit_studio_project import sources_current
from .media_native import capability

MAX_FONT_BYTES=16777216
MAX_PROJECT_BYTES=20971520
LIMITS=dict(startup_seconds=45,read_seconds=2,mutation_seconds=20,command_seconds=120,
    sessions_per_app=2,sessions_per_store=4,max_project_bytes=MAX_PROJECT_BYTES)


def source(store,app_id,job_id,version):
    """Recheck current approved brief/rights and exact frozen job inside SQLite."""
    identifier(job_id)
    if type(version) is not int or version<1:raise Invalid('Use the exact app manifest version')
    with connection(store.path) as db:
        app=db.execute('SELECT * FROM apps WHERE id=?',(app_id,)).fetchone()
        if app is None or app['version']!=version:raise Invalid('Studio app manifest changed')
        job=db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?',(app_id,job_id)).fetchone()
        if job is None or job['action']!='hypit_render':raise Invalid('Choose an app-owned Hypit source job')
        try:data=json.loads(job['data'])
        except (TypeError,ValueError):raise Invalid('Studio source job inputs are unreadable') from None
        current_inputs(db,store,app_id,data)
        return dict(app_hash=digest(json.loads(app['data'])),inputs=data,source_hash=digest(data))


def font_bytes(path):
    """Retain a bounded stable host-selected font without following reparse paths."""
    path=Path(path);parents_plain(path.parent);before=plain(path)
    if before.st_size>MAX_FONT_BYTES:raise Invalid('Studio font exceeds its byte bound')
    with path.open('rb') as stream:
        opened=os.fstat(stream.fileno());raw=stream.read(MAX_FONT_BYTES+1)
        finished=os.fstat(stream.fileno())
    after=plain(path)
    signatures={(p.st_dev,p.st_ino,p.st_size,p.st_mtime_ns) for p in (before,opened,finished,after)}
    if len(signatures)!=1 or len(raw)!=before.st_size or not raw:
        raise Invalid('Studio font changed during preparation')
    return raw


def parents_plain(path):
    """Validate all existing absolute path components, including Windows junctions."""
    path=Path(path).absolute()
    for parent in reversed([path,*path.parents]):plain(parent,directory=True)


def prepared(store,app_id,job_id,version,alive):
    alive();frozen=source(store,app_id,job_id,version)
    installation=discover();alive()
    selected=capability().get('font')
    if not selected:raise Invalid('Prepare a verified local font before Studio')
    font=font_bytes(selected);authored=project(frozen['inputs']['scene'])
    files={name:text.encode('utf-8') for name,text in authored['files'].items()}
    files['font.ttf']=font
    size=sum(len(raw) for raw in files.values())
    if size>MAX_PROJECT_BYTES:raise Invalid('Studio complete project exceeds its byte bound')
    hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}
    summary=dict(schema='wmm.studio-execution-summary.v1',app_id=app_id,manifest_version=version,
        app_hash=frozen['app_hash'],source_job_id=job_id,source_hash=frozen['source_hash'],
        source_profile='APPROVED_BRIEF_CAPTIONS',installation=public_summary(installation),
        staged_hashes=hashes,project_bytes=size,limits=dict(LIMITS),
        effects=['START_OWNED_LOCAL_STUDIO','COMPILE_PRIVATE_SOURCE','START_PRIVATE_LOCAL_MEDIA_WORKER'],
        provider_calls='NOT_PERMITTED_BY_PROFILE',publication='NOT_RUN')
    intent=dict(manifest_version=version,app_hash=frozen['app_hash'],source_job_id=job_id,
        source_hash=frozen['source_hash'],summary_hash=digest(summary),installation_id=installation['id'])
    if source(store,app_id,job_id,version)!=frozen:raise Invalid('Studio source changed during planning')
    return dict(summary=summary,intent=intent,files=files,installation=installation,font_path=selected)


def private_folder(store,app_id,identity):
    """Only internal app hashes and registry UUIDs select fresh storage."""
    identifier(identity);base=store.path.parent.absolute();parents_plain(base)
    for name in ('studio',digest(app_id)):
        base=base/name
        try:base.mkdir()
        except FileExistsError:pass
        plain(base,directory=True)
    folder=base/identity
    folder.mkdir(exist_ok=False);plain(folder,directory=True)
    return folder


def exact_reservation(store,app_id,identity,version,intent):
    row=Registry(store).read(app_id,identity)
    if type(version) is not int or row['version']!=version or row['state']!='PREPARED' or row['intent']!=intent:
        raise Invalid('Studio startup reservation changed')
    return row


class Factory:
    def __init__(self,store):self.store=store

    def plan(self,app_id,body,alive=lambda:None):
        if type(body) is not dict or set(body)!={'source_job_id','manifest_version'}:
            raise Invalid('Use exact Studio source job and manifest fields')
        value=prepared(self.store,app_id,body['source_job_id'],body['manifest_version'],alive)
        return dict(summary=value['summary'],summary_hash=value['intent']['summary_hash'],
            intent=value['intent'],native_execution='NOT_STARTED')

    def create(self,app_id,identity,registry_version,alive):
        """Internal manager owns one-time launch permission; this creates only files."""
        row=Registry(self.store).read(app_id,identity);intent=row['intent']
        exact_reservation(self.store,app_id,identity,registry_version,intent)
        value=prepared(self.store,app_id,intent['source_job_id'],intent['manifest_version'],alive)
        if value['intent']!=intent:raise Invalid('Studio reviewed execution summary changed')
        revalidate(value['installation']);alive()
        exact_reservation(self.store,app_id,identity,registry_version,intent)
        folder=private_folder(self.store,app_id,identity);info=plain(folder,directory=True)
        for name,raw in value['files'].items():
            alive()
            with (folder/name).open('xb') as stream:stream.write(raw)
        revalidate(value['installation']);alive()
        if hashlib.sha256(font_bytes(value['font_path'])).hexdigest()!=value['summary']['staged_hashes']['font.ttf']:
            raise Invalid('Studio font changed after staging')
        current=source(self.store,app_id,intent['source_job_id'],intent['manifest_version'])
        if current['app_hash']!=intent['app_hash'] or current['source_hash']!=intent['source_hash']:
            raise Invalid('Studio source changed after staging')
        parents_plain(folder)
        final=plain(folder,directory=True)
        if (info.st_dev,info.st_ino)!=(final.st_dev,final.st_ino):raise Invalid('Studio directory was replaced')
        sources=value['summary']['staged_hashes'];sources_current(folder,sources)
        if set(p.name for p in folder.iterdir())!=set(sources):raise Invalid('Studio staged file set changed')
        exact_reservation(self.store,app_id,identity,registry_version,intent)
        return StudioProcess(folder,value['installation'],sources,
            dict(root='film.svml',files=['build.svrun','film.svml','style.svs']),alive)
