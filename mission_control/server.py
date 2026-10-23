"""Loopback-only Mission Control server. Run: python -m mission_control.server."""
import argparse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse, unquote, parse_qs
from .common import Invalid, canonical, digest
import hashlib
from .store import Store
from .service import Service
from .worker import Runner
from .operator_identity import Identities

STATIC=Path(__file__).resolve().parent/"static"


def media_range(value,size):
    """Parse one bounded byte range; reject malformed, multipart or unsatisfiable input."""
    match=re.fullmatch(r"bytes=(\d*)-(\d*)",value)
    if not match or not any(match.groups()):raise Invalid("Invalid video byte range")
    left,right=match.groups()
    if not left:
        length=int(right)
        if length<=0:raise Invalid("Invalid video suffix range")
        return max(0,size-length),size-1
    start=int(left);end=min(int(right),size-1) if right else size-1
    if start>=size or start>end:raise Invalid("Video byte range is unavailable")
    return start,end


class Server(ThreadingHTTPServer):
    daemon_threads=True

    def __init__(self,address,store,operator="local-operator"):
        if address[0]!="127.0.0.1":
            raise Invalid("Mission Control may bind only to 127.0.0.1")
        super().__init__(address,Handler)
        self.service=Service(store,operator)
        source=Path(__file__).resolve().parent
        files=sorted([*source.glob("*.py"),*source.glob("*.ps1"),*source.glob("static/*"),*source.glob("sdk/*.mjs")])
        self.service.build_id=digest({str(path.relative_to(source)):hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()})
        self.sessions={}
        self.identities=Identities()
        self.runner=Runner(store)
        from .audit_worker import AuditWorker
        self.audit_runner=AuditWorker(store)
        self.service.worker_health=lambda:dict(self.runner.health)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,format,*args):
        """Avoid logging request paths or sensitive provider references to console."""
        return

    def send(self,code,body,content_type="application/json; charset=utf-8",filename=None,headers=None):
        """Return a bounded response with cache, content, framing and cookie protection."""
        raw=body if isinstance(body,bytes) else canonical(body).encode()
        self.send_response(code)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if getattr(self,"new_cookie",None):
            self.send_header("Set-Cookie",f"growth_session={self.new_cookie}; HttpOnly; SameSite=Strict; Path=/")
        if filename:
            self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
        for key,value in (headers or {}).items():self.send_header(key,value)
        self.end_headers()
        self.wfile.write(raw)

    def session(self):
        """Establish a local HttpOnly session with its bound anti-CSRF token."""
        jar=cookies.SimpleCookie()
        jar.load(self.headers.get("Cookie",""))
        session_id=jar["growth_session"].value if "growth_session" in jar else ""
        if session_id not in self.server.sessions:
            if len(self.server.sessions)>=256:
                raise Invalid("Session limit reached; restart the local server")
            session_id=secrets.token_urlsafe(32)
            self.server.sessions[session_id]=secrets.token_urlsafe(32)
            self.new_cookie=session_id
        return self.server.sessions[session_id]

    def boundary(self,write=False):
        """Reject another host, cross-origin write or invalid session token."""
        expected=f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host")!=expected:
            raise PermissionError("Use the exact local Mission Control address")
        csrf=self.session()
        if write:
            if self.headers.get("Origin",f"http://{expected}")!=f"http://{expected}":
                raise PermissionError("Cross-origin request rejected")
            if not secrets.compare_digest(self.headers.get("X-CSRF-Token",""),csrf):
                raise PermissionError("Session expired; reload before saving")
        return csrf

    def do_GET(self):
        """Dispatch read-only API and static workspace requests through boundary checks."""
        self.dispatch(False)

    def do_POST(self):
        """Dispatch write requests only after host, session and CSRF validation."""
        self.dispatch(True)

    def dispatch(self,write):
        """Return clear input errors and preserve existing state on operational failure."""
        try:
            path=urlparse(self.path).path
            webhook=self.webhook_handler(path) if write else None
            if webhook:
                return webhook(path)
            token=self.boundary(write)
            if write:
                return self.post(path)
            return self.get(path,token)
        except PermissionError as exc:
            self.send(403,{"error":str(exc)})
        except KeyError:
            self.send(404,{"error":"This app, record or route does not exist"})
        except (Invalid,ValueError,TypeError) as exc:
            self.send(400,{"error":str(exc)})
        except (ConnectionAbortedError,BrokenPipeError,ConnectionResetError):
            return
        except Exception:
            self.send(500,{"error":"The local operation failed. Your existing records are preserved; retry after checking the server."})

    def webhook_handler(self,path):
        """Recognize only the original exact signed-delivery routes before CSRF."""
        routes=((r'/api/payments/[a-z0-9-]+/[a-f0-9-]{36}',self.payment_webhook),
                (r'/api/storekit/[a-z0-9-]+/[a-f0-9-]{36}',self.storekit_webhook),
                (r'/api/attribution/[a-z0-9-]+/[a-f0-9-]{36}/[a-f0-9-]{36}/[1-9][0-9]{0,6}',self.attribution_webhook))
        return next((handler for pattern,handler in routes if re.fullmatch(pattern,path)),None)

    def get(self,path,token):
        """Serve the fixed UI routes and app-scoped read endpoints."""
        callback=self.callback_page(path)
        if callback:
            return self.send(200,(STATIC/callback).read_bytes(),'text/html; charset=utf-8')
        if path=="/api/bootstrap":
            return self.send(200,dict(self.server.service.bootstrap(),csrf=token,identity=self.server.identities.public(token)))
        if path=="/api/weekly-review":
            return self.get_weekly_review()
        if path=="/api/research":
            root=Path(__file__).resolve().parents[1]/"package"
            return self.send(200,{"ledger":json.loads((root/"research-ledger.json").read_text(encoding="utf-8-sig")),"acquisition":json.loads((root/"acquisition-profiles.json").read_text(encoding="utf-8-sig"))})
        if path.startswith("/api/apps/"):
            return self.get_app(path)
        scripts=('/subscription-authoring.js','/customer-workflow.js','/growth-review.js','/page-reporting.js','/setup-discovery.js','/google-play.js','/play-callback.js','/social-access.js','/social-callback.js','/agent-access.js','/insights.js','/storekit.js','/attribution.js','/guided-workflow.js','/subscriptions.js',
                 '/workflow-automation.js','/followup.js','/aeo.js','/public-store-readback.js',
                 '/pmf-workflow.js','/pmf-research.js','/audit-runtime.js','/automatic-preparation.js','/campaign-sequence.js','/experiment-tracking.js',
                 '/spytok-workflow.js','/production-feasibility.js','/spira-workflow.js','/journey-readiness.js')
        if path in scripts:
            return self.send(200,(STATIC/path[1:]).read_bytes(),"text/javascript; charset=utf-8")
        files={"/":"index.html","/index.html":"index.html","/style.css":"style.css","/page-reporting.css":"page-reporting.css","/app.js":"app.js","/creative-ranking.js":"creative-ranking.js","/acquisition.js":"acquisition.js","/creative-rendering.js":"creative-rendering.js","/verified-review.js":"verified-review.js","/provider-actions.js":"provider-actions.js","/outcome-learning.js":"outcome-learning.js","/signed-payments.js":"signed-payments.js"}
        if path not in files:
            raise KeyError(path)
        file=STATIC/files[path]
        return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0]+"; charset=utf-8")

    def get_weekly_review(self):
        """Parse only the closed portfolio offset before a bounded saved-evidence read."""
        from .weekly_inbox import review
        query=urlparse(self.path).query
        if query and not re.fullmatch(r'offset=(0|[1-9][0-9]{0,8})',query):
            raise Invalid('Use only the weekly review offset')
        return self.send(200,review(self.server.service,int(query.split('=')[1]) if query else 0))

    def callback_page(self,path):
        """Serve local callback assets without processing provider codes in a GET."""
        if re.fullmatch(r'/social/callback/(facebook|instagram|tiktok|linkedin)',path):
            return 'social-callback.html'
        if path not in ('/','/index.html'):return None
        query=parse_qs(urlparse(self.path).query,keep_blank_values=True,max_num_fields=20)
        if 'state' in query and ('code' in query or 'error' in query):return 'play-callback.html'
        return None

    def get_app(self,path):
        """Resolve only the selected workspace, snapshot or validated image identifier."""
        parts=path.strip("/").split("/")
        if len(parts)<3:raise KeyError(path)
        app_id=parts[2]
        store=self.server.service.store
        if parts[3:]==['subscription-growth']:
            if urlparse(self.path).query:raise Invalid('Use the exact subscription review address')
            return self.send(200,self.server.service.subscription_review(app_id))
        if parts[3:]==['subscription-growth','history']:
            if urlparse(self.path).query:raise Invalid('Use the exact growth review history address')
            from .growth_review_store import GrowthReviews
            return self.send(200,GrowthReviews(store).list(app_id))
        if parts[3:]==['customer-workflows']:
            if urlparse(self.path).query:raise Invalid('Use the exact customer workflow history address')
            from .customer_workflow_store import CustomerWorkflows
            return self.send(200,CustomerWorkflows(store).list(app_id))
        if parts[3:]==['agent-operations']:
            if urlparse(self.path).query:raise Invalid('Use the exact app operation discovery address')
            from .agent_operations import discovery
            return self.send(200,discovery(store.app(app_id)))
        if len(parts)==3:
            return self.send(200,dict(self.server.service.workspace(app_id),identity=self.server.identities.public(self.session())))
        if len(parts)==6 and parts[3:5]==['social-access','flows']:
            return self.get_social_progress(app_id,parts[5])
        histories={('aeo','history'):'aeo',('attribution','history'):'attribution'}
        if tuple(parts[3:]) in histories:
            return self.get_history(app_id,histories[tuple(parts[3:])])
        scoped={'renders':self.get_video,'experiment-tracking':self.get_instrumentation,'files':self.get_asset,'setup-discovery':self.get_setup_discovery}
        if parts[3] in scoped:return scoped[parts[3]](parts)
        ordinary={'export':lambda:self.send(200,store.export(app_id),filename=app_id+'-snapshot.json'),
                  'measurement':lambda:self.get_measurement(app_id)}
        if len(parts)==4 and parts[3] in ordinary:
            return ordinary[parts[3]]()
        raise KeyError(path)

    def get_setup_discovery(self,parts):
        """Expose local setup detail with no request target or network side effect."""
        from .setup_http import get
        if urlparse(self.path).query:raise Invalid('Use the exact setup proposal address')
        return self.send(200,get(self.server.service.store,parts[2],parts[4:]))

    def get_instrumentation(self,parts):
        """Download the exact reviewed app-owned package without provider or install authority."""
        from .instrumentation import prepare,archive
        if urlparse(self.path).query or len(parts)!=8 or parts[5]!='instrumentation':
            raise Invalid('Use the current exact integration package address')
        value=prepare(self.server.service.store,parts[2],parts[4],parts[6],parts[7])
        return self.send(200,archive(value),'application/zip',filename='wmm-'+value['experiment_id']+'-instrumentation.zip')

    def get_social_progress(self,app_id,identity):
        """Keep exact social progress validation separate from general app routing."""
        from .social_flows import Flows,public
        if urlparse(self.path).query:raise Invalid('Use the exact social progress address')
        return self.send(200,public(Flows(self.server.service.store,self.server.server_port).get(app_id,identity)))

    def get_asset(self,parts):
        """Read only one validated image within the selected existing app."""
        if len(parts)!=5:raise KeyError(self.path)
        store=self.server.service.store;app_id=parts[2];store.app(app_id)
        if not re.fullmatch(r"[a-f0-9-]+\.(?:png|jpg|jpeg)",parts[4]):raise Invalid('Invalid asset identifier')
        file=store.path.parent/'files'/app_id/parts[4]
        return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0])

    def get_history(self,app_id,kind):
        """Export only registered app-scoped histories through exact addresses."""
        from .aeo_portable import export_aeo
        from .attribution_portable import export_attribution
        from .db import connection
        exporters={'aeo':export_aeo,'attribution':export_attribution}
        store=self.server.service.store
        store.app(app_id)
        if urlparse(self.path).query:
            raise Invalid('Use the exact app '+kind+' history address')
        with connection(store.path) as db:
            value=exporters[kind](db,app_id)
        return self.send(200,value,filename=app_id+'-'+kind+'-history.json')

    def get_measurement(self,app_id):
        """Preserve the existing optional as-of measurement query."""
        from .ledger import Ledger
        store=self.server.service.store
        store.app(app_id)
        query=parse_qs(urlparse(self.path).query)
        return self.send(200,Ledger(store.path).reports(app_id,query.get('as_of',[None])[0]))

    def get_video(self,parts):
        """Require the finite app-owned video preview/download route shape."""
        if len(parts)!=6 or parts[5] not in ("preview","download"):raise KeyError("Video route not found")
        return self.video(parts[2],parts[4],parts[5]=="download")

    def video(self,app_id,render_id,download=False):
        """Serve hash-validated app-owned video with actual seeking and download support."""
        from .creative_rendering import artifact_file
        path,_=artifact_file(self.server.service.store,app_id,render_id);raw=path.read_bytes()
        headers={"Accept-Ranges":"bytes"};filename=app_id+"-"+render_id+".mp4" if download else None
        value=self.headers.get("Range")
        if not value:return self.send(200,raw,"video/mp4",filename,headers)
        try:start,end=media_range(value,len(raw))
        except Invalid:return self.send(416,b"","video/mp4",headers=dict(headers,**{"Content-Range":f"bytes */{len(raw)}"}))
        headers["Content-Range"]=f"bytes {start}-{end}/{len(raw)}"
        return self.send(206,raw[start:end+1],"video/mp4",filename,headers)

    def payment_webhook(self,path):
        """Authenticate finite loopback delivery via HMAC, never a browser CSRF exemption."""
        from .signed_payments import Payments
        expected=f"127.0.0.1:{self.server.server_port}"
        if self.headers.get_all("Host")!=[expected] or urlparse(self.path).query:
            raise PermissionError("Use the exact loopback payment delivery address")
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length",[]))!=1:
            raise Invalid("Payment delivery needs one bounded Content-Length")
        signatures=self.headers.get_all("Stripe-Signature",[])
        if len(signatures)!=1:raise PermissionError("Use one Stripe-Signature header")
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
            raise Invalid("Payment delivery must be application/json")
        previous=self.connection.gettimeout()
        try:
            self.connection.settimeout(5)
            raw=self.body(262144)
        finally:self.connection.settimeout(previous)
        if len(raw)!=int(self.headers["Content-Length"]):raise Invalid("Payment body is truncated")
        parts=path.strip("/").split("/")
        return self.send(200,Payments(self.server.service.store).intake(parts[2],parts[3],raw,signatures[0]))

    def body(self,limit=1048576):
        """Read an explicitly bounded request body and reject invalid size."""
        length=int(self.headers.get("Content-Length","0"))
        if not 0<length<=limit:
            raise Invalid("Request is empty or exceeds the upload limit")
        return self.rfile.read(length)

    def storekit_webhook(self,path):
        """Finite loopback deliveries authenticate with Apple JWS; they cannot create browser sessions."""
        from .storekit_ingestion import Notifications
        expected=f"127.0.0.1:{self.server.server_port}"
        if self.headers.get_all("Host")!=[expected] or urlparse(self.path).query:
            raise PermissionError("Use the exact loopback StoreKit delivery address")
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length",[]))!=1:
            raise Invalid("StoreKit delivery needs one bounded Content-Length")
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
            raise Invalid("StoreKit delivery must be application/json")
        previous=self.connection.gettimeout()
        try:
            self.connection.settimeout(5)
            raw=self.body(262144)
        finally:self.connection.settimeout(previous)
        if len(raw)!=int(self.headers["Content-Length"]):raise Invalid("StoreKit body is truncated")
        parts=path.strip("/").split("/")
        return self.send(200,Notifications(self.server.service.store).ingest(parts[2],parts[3],raw))

    def post(self,path):
        """Parse finite object requests or process a bounded image upload."""
        service=self.server.service
        parts=path.strip("/").split("/")
        if len(parts)==4 and parts[:2]==["api","apps"] and parts[3]=="files":
            return self.send(201,service.upload(parts[2],unquote(self.headers.get("X-Filename","image.png")),self.body(8388608)))
        data=self.post_data(path,parts)
        if path=='/api/social/callback':
            from .social_callbacks import callback
            return self.send(200,callback(service.store,data,self.server.server_port))
        if parts[:2]==["api","identity"]:return self.post_identity(parts,data)
        ordinary={'/api/worker/retry':lambda:self.retry_worker(data),
                  '/api/play/callback':lambda:self.play_callback(data),
                  '/api/apps':lambda:self.send(201,service.store.save_app(data.get('id'),data.get('data',{}),data.get('version'))),
                  '/api/restore':lambda:self.send(201,service.store.restore(data))}
        if path in ordinary:
            return ordinary[path]()
        if len(parts)<4 or parts[:2]!=["api","apps"]:
            raise KeyError(path)
        return self.post_app(parts,data)

    def post_data(self,path,parts):
        """Keep original per-route byte limits and strict duplicate/nonfinite checks."""
        raw=self.attribution_body(path,parts) if any(k in parts for k in ('setup-discovery','play','attribution','agent-access','social-access','social')) else self.body(self.post_limit(path,parts))
        strict=any(kind in parts for kind in ('subscription-growth','customer-workflows','setup-discovery','play','attribution','insights','aeo','release-selection','agent-access','social-access','social')) or path=='/api/restore'
        if strict:
            from .payment_signature import unique_pairs,bounded_tree
            data=json.loads(raw,object_pairs_hook=unique_pairs,parse_constant=lambda _:(_ for _ in ()).throw(Invalid('Nonfinite JSON is forbidden')))
            bounded_tree(data)
        else:
            data=json.loads(raw)
        if not isinstance(data,dict):
            raise Invalid('Request must be a JSON object')
        return data

    def retry_worker(self,data):
        """Bind explicit shared-worker recovery to a current workspace session."""
        from .db import connection
        if urlparse(self.path).query or set(data)!={"app_id","manifest_version"} or type(data["manifest_version"]) is not int or not isinstance(data["app_id"],str):
            raise Invalid("Reload the current workspace before retrying automation")
        with connection(self.server.service.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT version FROM apps WHERE id=?",(data["app_id"],)).fetchone()
            if row is None or row["version"]!=data["manifest_version"]:
                raise Invalid("App setup changed; refresh saved work before retrying automation")
            result=self.server.runner.retry_failed()
        return self.send(200,result)

    def post_limit(self,path,parts):
        """Bound protected setup independently from snapshots and ordinary records."""
        if "storekit" in parts:return 262144
        if 'play' in parts:return 262144 if parts[-1]=='discover' else 24576
        if "attribution" in parts:return 2097152
        if any(kind in parts for kind in ('setup-discovery','connections','payments','insights','release-selection','agent-access','social-access','social')):
            return 8192
        if "identity" in parts:return 512
        if path=="/api/worker/retry":return 512
        if parts[-1:]==["public-listing"]:return 512
        return 33554432 if path=="/api/restore" else 1048576

    def attribution_body(self,path,parts):
        """Protected setup is finite and exact JSON, with no alternate HTTP framing."""
        if urlparse(self.path).query or self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length",[]))!=1:
            raise Invalid("Use one bounded attribution JSON request without a query")
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
            raise Invalid("Attribution requests must be application/json")
        previous=self.connection.gettimeout()
        try:
            self.connection.settimeout(5)
            raw=self.body(self.post_limit(path,parts))
        finally:self.connection.settimeout(previous)
        if len(raw)!=int(self.headers["Content-Length"]):raise Invalid("Attribution request is truncated")
        return raw

    def agent_access(self,app_id,parts,body):
        """Finite app-owned access operations cannot accept arbitrary commands."""
        from .agent_access import AgentAccess,detect
        from .agent_contract import exact
        from .agent_tasks import proposal,AgentWork
        store=self.server.service.store;store.app(app_id);access=AgentAccess(store)
        if len(parts)==2 and parts[1]=='disconnect':return access.disconnect(app_id,parts[0],body)
        if len(parts)!=1:raise KeyError('Agent connection action not found')
        if parts[0]=='cleanup':
            exact(body,());return access.cleanup(app_id)
        actions={'save':lambda:access.save(app_id,body),'routes':lambda:access.routes(app_id,body),
                 'proposal':lambda:proposal(store,app_id,body),'approve':lambda:AgentWork(store).start(app_id,body)}
        if parts[0]=='detect':
            exact(body,('provider',));return detect(body['provider'])
        if parts[0] not in actions:raise KeyError('Agent connection action not found')
        return actions[parts[0]]()

    def post_app(self,parts,data):
        """Dispatch only registered app-scoped write actions."""
        service=self.server.service
        if parts[3]=='social-access':
            from .social_http import post as social_post
            return self.send(200,social_post(service.store,parts[2],parts[4:],data,self.server.server_port))
        if parts[3]=='agent-access':
            return self.send(200,self.agent_access(parts[2],parts[4:],data))
        app_id,action=parts[2:4]
        if action=='subscription-growth':
            if parts[4:]!=['entries'] or urlparse(self.path).query:raise Invalid('Use the exact growth review entry address')
            from .growth_review_store import GrowthReviews
            return self.send(201,GrowthReviews(service.store).save(app_id,data))
        if action=='customer-workflows':
            if len(parts)!=4 or urlparse(self.path).query:raise Invalid('Use the exact customer workflow creation address')
            from .customer_workflow_store import CustomerWorkflows
            return self.send(201,CustomerWorkflows(service.store).save(app_id,data))
        if action == 'campaign-inputs' and len(parts) == 4:
            from .campaign_inputs import CampaignInputs
            if urlparse(self.path).query:
                raise Invalid('Use the exact campaign input collection address')
            return self.send(201,CampaignInputs(service.store).start(app_id,data))
        routes={"records":lambda:service.evidence(app_id,data),"jobs":lambda:service.queue(app_id,data),
                "reviews":lambda:service.prepare_review(app_id,data),"cohorts":lambda:service.cohort(app_id,data),"events":lambda:service.events(app_id,data)}
        handlers={"setup-discovery":self.post_setup_discovery,"play":self.post_play,"experiment-tracking":self.post_tracking,"sequences":self.post_sequence,"resolutions":self.post_resolution,"release-selection":self.post_release_selection,"inspections":self.post_inspection,
                  "pmf-research":self.post_pmf_research,"followup":self.post_followup,"aeo":self.post_aeo,
                  "insights":self.post_insights,"storekit":self.post_storekit,"attribution":self.post_attribution,
                  "connections":self.post_connection,"experiments":self.post_experiment,"references":self.post_reference,"production":self.post_production,"rankings":self.post_ranking,"acquisition":self.post_acquisition,"access":self.post_access,"verified-reviews":self.post_verified_review,"provider-actions":self.post_provider_action,"learning":self.post_learning,"payments":self.post_payments}
        if action in handlers:
            return handlers[action](parts,data)
        if len(parts)==4 and action in routes:
            return self.send(201,routes[action]())
        exact={('jobs',6,'cancel'):lambda:service.cancel(app_id,parts[4]),
               ('reviews',6,'record'):lambda:service.review(app_id,parts[4],data)}
        key=(action,len(parts),parts[-1])
        if key in exact:
            return self.send(200,exact[key]())
        raise KeyError("route")

    def post_tracking(self,parts,data):
        """Prepare exact tracking reads, approve their owned jobs or stop one saved run."""
        from .experiment_tracking import Tracking
        if urlparse(self.path).query:raise Invalid('Use the exact tracking action address')
        service=Tracking(self.server.service.store)
        if len(parts)==5 and parts[4]=='prepare':return self.send(200,service.prepare(parts[2],data))
        if len(parts)==5 and parts[4]=='approve':return self.send(201,service.approve(parts[2],data))
        if len(parts)==6 and parts[5]=='cancel':return self.send(200,service.cancel(parts[2],parts[4],data))
        raise Invalid('Use a current tracking proposal, approval or cancellation address')

    def post_sequence(self,parts,data):
        """Approve exact reviewed actions or stop owned work in the selected app only."""
        from .sequence_store import Sequences
        if urlparse(self.path).query:raise Invalid('Use the exact sequence action address')
        service=Sequences(self.server.service.store,self.server.service.operator)
        if len(parts)==5 and parts[4]=='approve':return self.send(201,service.approve(parts[2],data))
        if len(parts)==6 and parts[5]=='cancel':return self.send(200,service.cancel(parts[2],parts[4],data))
        raise Invalid('Use a current sequence approval or cancellation address')

    def post_resolution(self,parts,data):
        """Approve one exact app-bound read proposal; no arbitrary agent commands."""
        from .resolutions import Resolutions
        if len(parts)!=5 or parts[4]!='approve' or urlparse(self.path).query:
            raise Invalid('Use the exact resolution approval address')
        return self.send(201,Resolutions(self.server.service.store,self.server.service.operator).start(parts[2],data))

    def post_pmf_research(self,parts,data):
        """Preserve the fixed research kinds and explicit preview behavior."""
        from .pmf_research import Research
        if len(parts)!=5 or urlparse(self.path).query:
            raise Invalid('Use the exact research action address')
        kind=parts[4]
        if kind not in ('study','snapshot','receipt','preview'):
            raise Invalid('Unknown research action')
        result=Research(self.server.service.store).save(parts[2],'snapshot' if kind=='preview' else kind,data,preview=kind=='preview')
        return self.send(200 if kind=='preview' else 201,result)

    def post_followup(self,parts,data):
        """Keep exact follow-up preparation/download/save routing and limits."""
        from .followup import Followup
        if len(parts)!=5 or urlparse(self.path).query:
            raise Invalid('Use the exact follow-up action address')
        workflow=Followup(self.server.service.store)
        if parts[4]=='prepare':
            return self.send(201,workflow.prepare(parts[2],data))
        if parts[4]=='download':
            return self.send(200,workflow.download(parts[2],data.get('id')))
        return self.send(201,workflow.save(parts[2],parts[4],data))

    def post_aeo(self,parts,data):
        """Accept only the previously supported exact read-only AEO run action."""
        from .aeo_workflows import Checks
        if len(parts)!=5 or parts[4]!='run' or urlparse(self.path).query:
            raise Invalid('Use the exact app AEO run address')
        return self.send(201,Checks(self.server.service.store).run(parts[2],data))

    def post_insights(self,parts,data):
        """Local trusted operator consent and normal CSRF protect read-only analytics setup."""
        if urlparse(self.path).query:
            raise Invalid("Use the exact analytics action address without a query")
        from .insights import Insights
        insights=Insights(self.server.service.store)
        if len(parts)==5 and parts[4]=="setup":
            return self.send(201,insights.setup(parts[2],data))
        if len(parts)==6 and parts[5]=="read":
            return self.send(200,insights.refresh(parts[2],parts[4],data))
        if len(parts)==6 and parts[5]=="events":
            return self.send(200,insights.update_events(parts[2],parts[4],data))
        if len(parts)==6 and parts[5]=="disconnect":
            return self.send(200,insights.disconnect(parts[2],parts[4],data))
        raise KeyError("Analytics route not found")

    def post_storekit(self,parts,data):
        """Fresh app owner/maker identity protects source setup, manual verification and disconnect."""
        from .storekit_sources import Sources
        from .storekit_ingestion import Notifications
        user=self.server.identities.fresh(self.session())
        store=self.server.service.store
        if len(parts)==5 and parts[4]=="sources":
            return self.send(201,Sources(store).create(parts[2],user,data))
        if len(parts)==7 and parts[4]=="sources" and parts[6]=="disconnect":
            return self.send(200,Sources(store).disconnect(parts[2],parts[5],user,data))
        if len(parts)==7 and parts[4]=="sources" and parts[6]=="notifications":
            return self.send(201,Notifications(store).manual(parts[2],parts[5],user,data))
        raise KeyError("StoreKit action route not found")

    def attribution_webhook(self,path):
        """Finite loopback intake authenticates the original Apple signature and map hash."""
        from .attribution_ingestion import Observations
        expected=f"127.0.0.1:{self.server.server_port}"
        if self.headers.get_all("Host")!=[expected] or urlparse(self.path).query:
            raise PermissionError("Use the exact loopback attribution address")
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length",[]))!=1:
            raise Invalid("Attribution delivery needs one bounded Content-Length")
        hashes=self.headers.get_all("X-Attribution-Map-SHA256",[])
        if len(hashes)!=1 or not re.fullmatch(r"[a-f0-9]{64}",hashes[0]):
            raise Invalid("Use one exact conversion-map SHA256 header")
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":
            raise Invalid("Attribution delivery must be application/json")
        previous=self.connection.gettimeout()
        try:
            self.connection.settimeout(5)
            raw=self.body(262144)
        finally:self.connection.settimeout(previous)
        if len(raw)!=int(self.headers["Content-Length"]):raise Invalid("Attribution body is truncated")
        parts=path.strip("/").split("/")
        result=Observations(self.server.service.store).ingest(parts[2],parts[3],raw,parts[4],int(parts[5]),hashes[0])
        return self.send(200,result)

    def post_attribution(self,parts,data):
        """Fresh app roles protect declarations, immutable maps and explicit one-shot reads."""
        from .attribution_sources import Sources
        from .attribution_maps import Maps
        from .attribution_ingestion import Observations
        from .attribution_adservices import AdServices
        user=self.server.identities.fresh(self.session())
        store=self.server.service.store
        if len(parts)==5 and parts[4]=="sources":
            return self.send(201,Sources(store).create(parts[2],user,data))
        if len(parts)==5 and parts[4]=="maps":
            return self.send(201,Maps(store).save(parts[2],user,data))
        if len(parts)==7 and parts[4]=="sources":
            action=parts[6]
            if action=="disconnect":return self.send(200,Sources(store).disconnect(parts[2],parts[5],user,data))
            if action=="postbacks":return self.send(201,Observations(store).manual(parts[2],parts[5],user,data))
            if action=="adservices":return self.send(201,AdServices(store).read(parts[2],parts[5],user,data))
        raise KeyError("Attribution action route not found")

    def post_identity(self,parts,data):
        """Bind identity credentials to this existing CSRF-protected local session."""
        identities=self.server.identities;session=self.session()
        if parts==["api","identity","login"]:return self.send(200,identities.login(session,data))
        if parts==["api","identity","logout"] and not data:return self.send(200,identities.logout(session))
        raise KeyError("Identity route not found")

    def post_access(self,parts,data):
        """Require fresh authenticated identity before app-scoped owner/member changes."""
        from .review_access import Access
        access=Access(self.server.service.store);identities=self.server.identities
        if len(parts)!=5:raise KeyError("Access route not found")
        user=identities.fresh(self.session())
        if parts[4]=="bootstrap":return self.send(201,access.bootstrap(parts[2],user,data))
        if parts[4]=="members":
            target=identities.lookup(self.session(),data.get("login"))
            return self.send(200,access.save(parts[2],user,target,data))
        raise KeyError("Access route not found")

    def post_verified_review(self,parts,data):
        """Pass verified session identity, never body-supplied maker/checker names."""
        from .verified_reviews import Reviews
        reviews=Reviews(self.server.service.store)
        user=self.server.identities.fresh(self.session())
        if len(parts)==4:return self.send(201,reviews.prepare(parts[2],user,data))
        if len(parts)==6 and parts[5]=="approve":return self.send(200,reviews.approve(parts[2],parts[4],user,data))
        raise KeyError("Verified review route not found")

    def post_release_selection(self,parts,data):
        """Dispatch one bounded app-owned local release selection action."""
        from .release_selection import choose
        if len(parts)!=4 or urlparse(self.path).query:
            raise Invalid('Use the exact selected-release action address')
        return self.send(200,choose(self.server.service.store,parts[2],data))

    def post_connection(self,parts,data):
        """Handle only explicit protected setup and local disconnect operations."""
        from .connection_setup import Connections
        connections=Connections(self.server.service.store)
        if len(parts)==4:
            return self.send(201,connections.setup(parts[2],data))
        if len(parts)==6 and parts[5]=="disconnect":
            return self.send(200,connections.disconnect(parts[2],parts[4],data.get("version")))
        raise KeyError("Protected connection route not found")

    def post_setup_discovery(self,parts,data):
        """Use strict app-owned discover/apply/delete actions behind normal CSRF checks."""
        from .setup_http import post
        return self.send(200,post(self.server.service.store,parts[2],parts[4:],data))

    def post_play(self,parts,data):
        """Keep Play setup and reads inside the normal app/session/CSRF boundary."""
        from .play_http import post
        return self.send(200,post(self.server.service.store,parts[2],parts[4:],data,self.server.server_port))

    def play_callback(self,data):
        """Consume an exact single-use consent proof without accepting a return URL."""
        from .play_http import finish
        return self.send(200,finish(self.server.service.store,data,self.server.server_port))

    def post_inspection(self,parts,data):
        """Closed CSRF-protected native actions; no client results or arbitrary commands."""
        from .audit_runtime import Inspections
        from .audit_tools import capability
        if len(parts)!=5 or urlparse(self.path).query:raise Invalid("Use the exact inspection action address")
        flow=Inspections(self.server.service.store)
        flow.store.app(parts[2])
        operation=parts[4]
        if operation in ("view","detect"):
            if data:raise Invalid("Inspection read action has no fields")
            return self.send(200,dict(flow.view(parts[2]),worker=self.server.audit_runner.health) if operation=="view" else capability())
        if operation=="detail":
            from .audit_contract import exact
            exact(data,("id",))
            return self.send(200,flow.detail(parts[2],data["id"]))
        if operation not in ("save","queue","cancel"):raise Invalid("Unknown inspection action")
        return self.send(201,getattr(flow,operation)(parts[2],data))

    def post_provider_action(self,parts,data):
        """Authenticate finite exact-change operations; ordinary reviews cannot authorize them."""
        from .provider_outbox import Outbox
        if len(parts)==6 and parts[5]=="public-listing":
            from .public_store_readback import PublicStore
            return self.send(200,PublicStore(self.server.service.store).run(parts[2],parts[4],data))
        outbox=Outbox(self.server.service.store)
        user=self.server.identities.fresh(self.session())
        if len(parts)==5 and parts[4]=="destination":return self.send(200,outbox.destination(parts[2],user,data))
        if len(parts)==4:return self.send(201,outbox.prepare(parts[2],user,data))
        if len(parts)==6 and parts[5] in ("approve","execute","reconcile","cancel"):
            return self.send(200,getattr(outbox,parts[5])(parts[2],parts[4],user,data))
        raise KeyError("Provider action route not found")

    def post_payments(self,parts,data):
        """Require fresh owner/maker identity on ordinary CSRF-protected setup/read actions."""
        from .payment_sources import Sources
        from .signed_payments import Payments
        user=self.server.identities.fresh(self.session());store=self.server.service.store
        if len(parts)==5 and parts[4]=="sources":
            return self.send(201,Sources(store).create(parts[2],user,data))
        if len(parts)==7 and parts[4]=="sources" and parts[6]=="disconnect":
            return self.send(200,Sources(store).disconnect(parts[2],parts[5],user,data))
        if len(parts)==7 and parts[4]=="receipts" and parts[6]=="reconcile":
            return self.send(200,Payments(store).reconcile(parts[2],parts[5],user,data))
        raise KeyError("Payment action not found")

    def post_learning(self,parts,data):
        """Separate operator joins from freshly authenticated local guidance actions."""
        from .outcome_learning import Learning
        from .outcome_links import Links
        if len(parts)==5 and parts[4]=="links":return self.send(201,Links(self.server.service.store).save(parts[2],data))
        learning=Learning(self.server.service.store);user=self.server.identities.fresh(self.session())
        if len(parts)==4:return self.send(201,learning.propose(parts[2],user,data))
        if len(parts)==6 and parts[5]=="briefs":return self.send(201,learning.use(parts[2],parts[4],user,data))
        if len(parts)==6 and parts[5] in ("reserve","evaluate","approve","activate","rollback"):
            return self.send(200,learning.act(parts[2],parts[4],user,parts[5],data))
        raise KeyError("Local learning route not found")

    def post_experiment(self,parts,data):
        """Expose bounded local registration, evaluation and explicit lifecycle actions."""
        from .experiments import Experiments
        experiments=Experiments(self.server.service.store)
        if len(parts)==4:return self.send(201,experiments.create(parts[2],data))
        if len(parts)==6 and parts[5]=="actions":return self.send(200,experiments.act(parts[2],parts[4],data))
        if len(parts)==6 and parts[5]=="evaluate" and not data:return self.send(200,experiments.evaluate(parts[2],parts[4]))
        if len(parts)==6 and parts[5]=="schedule":
            from .experiment_schedules import Schedules
            return self.send(200,Schedules(self.server.service.store).save(parts[2],parts[4],data))
        raise KeyError("Experiment route not found")

    def post_reference(self,parts,data):
        """Scope source save, preview and explicit import to the chosen workspace."""
        from .creative_library import Library
        library=Library(self.server.service.store)
        if len(parts)==4:return self.send(201,library.save(parts[2],data))
        if len(parts)==5 and parts[4]=="preview":return self.send(200,library.preview(parts[2],data))
        if len(parts)==5 and parts[4]=="import":return self.send(201,library.commit(parts[2],data))
        raise KeyError("Source library route not found")

    def post_ranking(self,parts,data):
        """Expose only explicit scoped relevance, policy and saved ranking actions."""
        from .creative_ranking import Rankings
        ranking=Rankings(self.server.service.store)
        if len(parts)==5 and parts[4] in ("policy","relevance"):return self.send(201,ranking.save(parts[2],parts[4],data))
        if len(parts)==5 and parts[4]=="run":return self.send(201,ranking.run(parts[2],data))
        raise KeyError("Ranking route not found")

    def post_production(self,parts,data):
        """Accept only scoped inspection and original brief preparation actions."""
        from .creative_analysis import Analyses
        from .creative_briefs import Briefs
        from .creative_rendering import Renders
        from .production_feasibility import Capabilities
        store=self.server.service.store
        if len(parts)==5 and parts[4] in ("profile","requirement"):return self.send(201,Capabilities(store).save(parts[2],parts[4],data))
        if len(parts)==5 and parts[4]=="analyses":return self.send(201,Analyses(store).save(parts[2],data))
        if len(parts)==5 and parts[4]=="briefs":return self.send(201,Briefs(store).save(parts[2],data))
        if len(parts)==5 and parts[4]=="renders":return self.send(201,Renders(store).queue(parts[2],data))
        raise KeyError("Creative production route not found")

    def post_acquisition(self,parts,data):
        """Accept guided source-bound preparation and explicit evidence attachment only."""
        from .acquisition_workflows import Acquisition
        acquisition=Acquisition(self.server.service.store)
        if len(parts)!=5:raise KeyError("Acquisition route not found")
        if parts[4] in ("intents","panels","observations"):return self.send(201,acquisition.save(parts[2],parts[4],data))
        if parts[4]=="reports":return self.send(201,acquisition.report(parts[2],data))
        if parts[4]=="attach":return self.send(201,acquisition.attach(parts[2],data))
        raise KeyError("Acquisition route not found")


def check_timezone_support():
    """Fail before startup if Windows lacks the declared timezone prerequisite."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo('America/Toronto')
    except ZoneInfoNotFoundError as exc:
        raise Invalid('Timezone data is missing. Run python -m pip install --require-hashes -r requirements.txt, then restart WMM.') from exc


def main():
    """Start the loopback-only local service and close its worker cleanly."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--database",type=Path,default=Path(__file__).resolve().parent/"data/mission-control.sqlite3")
    parser.add_argument("--operator",default="local-operator")
    args=parser.parse_args()
    try:
        check_timezone_support()
    except Invalid as exc:
        parser.error(str(exc))
    server=Server(("127.0.0.1",args.port),Store(args.database),args.operator)
    server.runner.start()
    server.audit_runner.start()
    print(f"Mission Control: http://127.0.0.1:{server.server_port}",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.runner.stop()
        server.audit_runner.stop()
        server.server_close()


if __name__=="__main__":
    main()
