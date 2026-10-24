"""Validate an internally approved Studio source bundle and its local-only profile."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
from .common import Invalid
from .hypit_installation import plain,file_hash


def source_path(folder,name):
    """Only canonical project-relative files from the trusted frozen bundle."""
    if not isinstance(name,str) or not name or ':' in name or '\\' in name:
        raise Invalid('Studio source path is unsupported')
    relative=PurePosixPath(name)
    if relative.is_absolute() or relative.as_posix()!=name or any(p in ('.','..') for p in relative.parts):
        raise Invalid('Studio source must remain inside its owned project')
    path=Path(folder)
    plain(path,directory=True)
    for part in relative.parts[:-1]:
        path=path/part;plain(path,directory=True)
    return path/relative.name


def sources_current(folder,sources):
    """No request-supplied source code is admitted here; the broker owns this bundle."""
    if not isinstance(sources,dict) or not {'build.svrun','runtime.json','package.json'}<=set(sources):
        raise Invalid('Studio needs its frozen Run, runtime and project manifest')
    for name,expected in sources.items():
        if not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):
            raise Invalid('Studio source hash is invalid')
        if file_hash(source_path(folder,name))[0]!=expected:
            raise Invalid('Studio project source changed; inspect before continuing')


def local_profile(folder):
    """The first adapter profile permits only the known installed local endpoints."""
    path=source_path(folder,'runtime.json');plain(path)
    with path.open('rb') as stream:raw=stream.read(1048577)
    if len(raw)>1048576:raise Invalid('Studio runtime profile exceeds its bound')
    try:value=json.loads(raw)
    except (ValueError,TypeError):raise Invalid('Studio runtime profile is invalid') from None
    expected=dict(format='hypit.runtime-local@1',dataRoot='.hypit/runtimes/local',endpoints={
        'html.local':dict(use='@hypit/provider-html-local',config=dict(defaultConcurrency=1,workers=1)),
        'media.local':dict(use='@hypit/media-local',config=dict(defaultConcurrency=1))})
    if value!=expected:raise Invalid('Studio requires the approved private local-only runtime profile')
    return value


def runtime_directory(folder,expected=None,create=False):
    """Bind real directory identities; runtime cleanup must never follow a link."""
    folder=Path(folder);path=folder;identities=[]
    for relative in ('.','.hypit','.hypit/runtimes','.hypit/runtimes/local'):
        path=folder/relative
        if create and relative!='.':
            try:path.mkdir(exist_ok=relative!='.hypit/runtimes/local')
            except FileExistsError:
                plain(path,directory=True)
                raise Invalid('Studio runtime storage already exists; inspect without adopting it') from None
        info=plain(path,directory=True)
        if not info.st_ino:raise Invalid('Studio runtime storage lacks a usable directory identity')
        identities.append(dict(relative=relative,device=info.st_dev,inode=info.st_ino,
                               resolved=str(path.resolve())))
    if expected is not None and identities!=expected:
        raise Invalid('Studio runtime directory changed; inspect without shutting down another runtime')
    return identities


def cleanup_current(folder,sources,runtime_identity):
    """Caption/source edits must not prevent stopping an unchanged owned runtime."""
    if runtime_identity is None:raise Invalid('Studio runtime directory ownership is unavailable')
    runtime_directory(folder,runtime_identity)
    for name in ('runtime.json','package.json'):
        if file_hash(source_path(folder,name))[0]!=sources[name]:
            raise Invalid('Studio cleanup profile or project manifest changed; inspect the owned runtime')
    local_profile(folder)


def snapshot_current(folder,sources,compiled,value):
    """Bind the actual compiled Run/Author closure; native IDs stay internal."""
    if not isinstance(value,dict) or type(value.get('revision')) is not int or value['revision']<1:
        raise Invalid('Studio returned an unsupported snapshot')
    if not isinstance(value.get('run'),dict) or value['run'].get('path')!='build.svrun':
        raise Invalid('Studio returned a foreign Run')
    snapshot_sources(folder,sources,compiled,value.get('source'))
    if not isinstance(value.get('tracks'),list):raise Invalid('Studio compiled tracks are unavailable')
    return value


def compiled_current(folder,sources,compiled):
    """The approved caller freezes the root and exact closure, never the response."""
    expected=compiled_files(compiled)
    for name in expected:
        source_path(folder,name)
        if name not in sources:raise Invalid('Studio compiled source is outside its approved bundle')
    return expected


def compiled_files(compiled):
    """Validate the independently admitted root and finite source membership."""
    if not isinstance(compiled,dict) or set(compiled)!={'root','files'}:
        raise Invalid('Studio needs an independently frozen compiled source closure')
    files=compiled['files']
    if not isinstance(files,list) or not files or any(not isinstance(p,str) for p in files):
        raise Invalid('Studio compiled source contract is invalid')
    if len(set(files))!=len(files) or compiled['root'] not in files or 'build.svrun' not in files:
        raise Invalid('Studio compiled source contract is incomplete')
    return set(files)


def snapshot_sources(folder,sources,compiled,source):
    """Require one exact declared source closure with no duplicate entries."""
    expected=compiled_current(folder,sources,compiled)
    files=source.get('files') if isinstance(source,dict) else None
    if not isinstance(files,list) or not files:raise Invalid('Studio compiled source closure is unavailable')
    seen=set()
    for item in files:
        compiled_file(folder,sources,item,seen)
    if seen!=expected or source.get('path')!=compiled['root']:
        raise Invalid('Studio compiled source closure is incomplete')
    return seen


def compiled_file(folder,sources,item,seen):
    """Bind one source text to its approved hash before retaining its identity."""
    if not isinstance(item,dict) or not isinstance(item.get('text'),str):
        raise Invalid('Studio compiled source is unsupported')
    name=item.get('path');source_path(folder,name)
    if name in seen or name not in sources or hashlib.sha256(item['text'].encode()).hexdigest()!=sources[name]:
        raise Invalid('Studio compiled source differs from the frozen project')
    seen.add(name)
