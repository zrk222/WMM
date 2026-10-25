"""Internal owned parameter transactions; the caller enforces actual approval."""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from urllib.parse import urlsplit
from .common import Invalid,canonical,digest,identifier
from .hypit_control_view import ControlView,finite
from .hypit_installation import plain,file_hash,revalidate
from .hypit_source_ledger import SourceLedger,source_bundle,source_file,MAX_SOURCE_BYTES
from .hypit_studio_http import session_bytes,parameter_bytes
from .hypit_studio_project import source_path,sources_current,local_profile,runtime_directory,snapshot_current,compiled_files

MUTATION_SECONDS=20
MAX_RESPONSE_BYTES=8388608


def source_text(folder,names):
    """Read only approved Run/Author files with stable file identities and bounds."""
    result={};size=0
    for name in sorted(names):
        source_file(name,'');path=source_path(folder,name);before=plain(path)
        with path.open('rb') as stream:
            opened=os.fstat(stream.fileno());raw=stream.read(MAX_SOURCE_BYTES-size+1)
        after=plain(path)
        identities=[(item.st_dev,item.st_ino) for item in (before,opened,after)]
        if len(set(identities))!=1:raise Invalid('Studio source file identity changed during observation')
        size+=len(raw)
        if size>MAX_SOURCE_BYTES:raise Invalid('Studio source closure exceeds its byte bound')
        try:result[name]=raw.decode('utf-8')
        except UnicodeError:raise Invalid('Studio source must be valid UTF8') from None
    return result


def edit_body(value):
    value=finite(value)
    if not isinstance(value,dict) or set(value)!={'request_key','base_version','base_hash','parameter'}:
        raise Invalid('Use the exact broker parameter request fields')
    parameter=value['parameter']
    if not isinstance(parameter,dict) or set(parameter)!={'revision','view_hash','owner_id','field_id','value'}:
        raise Invalid('Use the exact compiled parameter fields')
    return value


class ParameterBroker:
    """One live owned object; never restore native authority from saved PID/URL."""
    def __init__(self,store,app_id,project_id,session,admit):
        identifier(project_id)
        if not callable(admit):raise Invalid('Studio broker requires a trusted authority callback')
        self.store=store;self.app_id=app_id;self.project_id=project_id;self.session=session;self.admit=admit
        app=store.app(app_id);self.manifest=app['version'];self.app_hash=digest(app['data'])
        self.names=compiled_files(session.compiled)
        for name in self.names:source_file(name,'')
        self.immutable={name:sha for name,sha in session.sources.items() if name not in self.names}
        info=plain(session.folder,directory=True);self.directory=(info.st_dev,info.st_ino)
        self.scope=dict(app_id=app_id,session_id=str(uuid.uuid4()));self.key=secrets.token_bytes(32)
        self.ledger=SourceLedger(store);self.lock=threading.RLock();self.operation=None;self.started=False
        self.original_alive=session.alive;session.alive=self.alive

    def authority(self,action,body):
        app=self.store.app(self.app_id)
        if app['version']!=self.manifest or digest(app['data'])!=self.app_hash:
            raise PermissionError('Studio app context changed')
        scope=dict(app_id=self.app_id,project_id=self.project_id,manifest_version=self.manifest,
            installation_id=self.session.installation['id'],project_input_hash=digest(self.session.sources),
            compiled_hash=digest(self.session.compiled),request=copy.deepcopy(body))
        actor=self.admit(action,scope)
        if type(actor) is not str or not actor.strip() or len(actor)>100:
            raise PermissionError('Fresh trusted Studio authority is required')
        return actor

    @contextmanager
    def admitted(self,action,body):
        actor=self.authority(action,body);previous=self.operation
        self.operation=(action,body,actor)
        try:yield actor
        finally:self.operation=previous

    def alive(self):
        self.original_alive()
        if self.operation is None:raise PermissionError('Studio requires a current broker operation')
        action,body,actor=self.operation
        if self.authority(action,body)!=actor:raise PermissionError('Studio caller identity changed')

    def owned(self):
        self.alive();session=self.session;info=plain(session.folder,directory=True)
        if (info.st_dev,info.st_ino)!=self.directory:raise Invalid('Studio project directory changed')
        if session.closed or session.process is None or session.process.poll() is not None:
            raise Invalid('Owned Studio is not running; inspect retained history')
        if not session.process.owns_listener(urlsplit(session.origin).port):
            raise Invalid('Studio listener no longer belongs to its owned child job')
        if session.runtime_identity is None:raise Invalid('Studio runtime directory ownership is unavailable')
        session.logs_current();local_profile(session.folder)
        runtime_directory(session.folder,session.runtime_identity)
        for name,sha in self.immutable.items():
            if file_hash(source_path(session.folder,name))[0]!=sha:
                raise Invalid('Studio immutable project input changed')

    def observed(self):
        """Observe provisional source without adopting any changed source hash."""
        self.owned();before=source_text(self.session.folder,self.names)
        raw=session_bytes(self.session.origin,self.owned,time.monotonic()+2,MAX_RESPONSE_BYTES)
        try:snapshot=json.loads(raw)
        except ValueError:raise Invalid('Studio observation is not valid JSON') from None
        after=source_text(self.session.folder,self.names)
        if before!=after:raise Invalid('Studio source changed during observation')
        hashes=dict(self.session.sources,**{name:hashlib.sha256(text.encode()).hexdigest() for name,text in after.items()})
        snapshot_current(self.session.folder,hashes,self.session.compiled,snapshot)
        sources_current(self.session.folder,hashes);self.owned()
        bundle=source_bundle(dict(upstream_revision=snapshot['revision'],root=self.session.compiled['root'],files=after))
        return snapshot,bundle,hashes

    def view(self,snapshot):return ControlView(self.scope,snapshot,self.key)

    def start(self):
        with self.lock,self.admitted('start',{}):
            if self.started:raise Invalid('Studio broker already started')
            try:
                if self.session.state=='NEW':self.session.start()
                elif self.session.state!='READY':raise Invalid('Studio cannot attach this session state')
                snapshot,bundle,_=self.observed()
                head=self.ledger.initialize(self.app_id,self.project_id,{k:bundle[k] for k in ('upstream_revision','root','files')})
                self.started=True
                return dict(controls=self.view(snapshot).public(),source_head=head,execution='OWNED_SESSION_OBSERVED')
            except BaseException:
                self.session.close();raise

    def current(self):
        if not self.started:raise Invalid('Start the owned Studio broker first')
        sources_current(self.session.folder,self.session.sources)
        snapshot,bundle,hashes=self.observed();head=self.ledger.read(self.app_id,self.project_id)['head']
        if (head['upstream_revision'],head['content_hash'])!=(bundle['upstream_revision'],bundle['content_hash']):
            raise Invalid('Studio observation differs from retained source history; inspect without editing')
        return snapshot,bundle,hashes,head

    def read(self):
        with self.lock,self.admitted('read',{}):
            snapshot,_,_,head=self.current()
            return dict(controls=self.view(snapshot).public(),source_head=head,execution='OBSERVED_ONLY')

    def inspect(self):
        """Unresolved work remains inspect-only even if a fresh snapshot is readable."""
        with self.lock,self.admitted('inspect',{}):
            if not self.started:raise Invalid('Start the owned Studio broker first')
            snapshot,bundle,_=self.observed()
            history=self.ledger.read(self.app_id,self.project_id)
            return dict(controls=self.view(snapshot).public(),source_head=history['head'],attempts=history['attempts'],
                observed_source_hash=bundle['content_hash'],execution='INSPECT_ONLY_NO_RECONCILIATION',resend_allowed=False)

    def edit(self,value):
        body=edit_body(value)
        with self.lock,self.admitted('edit',body) as actor:
            if not self.started:raise Invalid('Start the owned Studio broker first')
            intent=dict(request_key=body['request_key'],base_version=body['base_version'],base_hash=body['base_hash'],
                view_hash=body['parameter']['view_hash'],proposal_hash=digest(body['parameter']),actor=actor)
            previous=self.ledger.retry(self.app_id,self.project_id,intent)
            if previous is not None:
                self.alive();return dict(attempt=previous,execution='NOT_RESENT')
            if self.session.state!='READY':raise Invalid('Studio requires inspection before another edit')
            snapshot,_,_,_=self.current();native=self.view(snapshot).parameter(body['parameter'])
            revalidate(self.session.installation);self.owned()
            prepared=self.ledger.prepare(self.app_id,self.project_id,intent)
            if not prepared['dispatch_allowed']:return dict(attempt=prepared,execution='NOT_RESENT')
            return self.dispatch(native,prepared)

    def before_send(self):
        self.owned();sources_current(self.session.folder,self.session.sources)

    def dispatch(self,native,prepared):
        try:
            status,raw=parameter_bytes(self.session.origin,canonical(native).encode(),self.owned,
                time.monotonic()+MUTATION_SECONDS,MAX_RESPONSE_BYTES,before_send=self.before_send)
            try:response=json.loads(raw)
            except ValueError:raise Invalid('Studio mutation result is not valid JSON') from None
            snapshot,bundle,hashes=self.observed()
            if status==200:
                if not isinstance(response,dict) or set(response)!={'revision'} or type(response['revision']) is not int or response['revision']!=snapshot['revision']:
                    raise Invalid('Studio mutation revision is unconfirmed')
                outcome='APPLIED'
            else:
                if status not in (400,403,409,422):
                    raise Invalid('Studio mutation outcome is uncertain; inspect without resending')
                if not isinstance(response,dict) or set(response)!={'error'} or not isinstance(response['error'],str):
                    raise Invalid('Studio mutation rejection is unconfirmed')
                outcome='REJECTED'
            controls=self.view(snapshot).public()
            revalidate(self.session.installation);self.owned()
            sources_current(self.session.folder,hashes)
            result=self.ledger.finish(self.app_id,self.project_id,prepared['id'],outcome,
                {k:bundle[k] for k in ('upstream_revision','root','files')})
        except BaseException:
            try:self.ledger.uncertain(self.app_id,self.project_id,prepared['id'])
            except Exception:pass  # PREPARED still blocks resend if authority/DB prevents this update.
            raise
        self.session.sources=hashes
        try:self.session.record('READY')
        except Exception:self.session.state='NEEDS_INSPECTION'
        head=self.ledger.read(self.app_id,self.project_id)['head'];self.alive()
        return dict(attempt=result,controls=controls,source_head=head,
            execution='UPSTREAM_PARAMETER_RESULT_OBSERVED',session_state=self.session.state)

    def close(self):
        """Revocation cannot strand an already-owned child/runtime."""
        with self.lock:
            self.session.close()
            return dict(app_id=self.app_id,session_id=self.scope['session_id'],state=self.session.state,closed=self.session.closed)
