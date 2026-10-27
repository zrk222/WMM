"""Local temporary fixture for rendered checklist acceptance; no real identity/media."""
from pathlib import Path
import json,tempfile
from mission_control.store import Store
from mission_control.server import Server
from mission_control.packaging_store import Packaging
from mission_control.review_access import Access
from mission_control.common import digest
from mission_control import operator_identity
from tests.test_creative_production import ready_production
from tests.test_packaging import draft,ref
from tests import test_verified_review as identities
operator_identity.github_read=identities.synthetic_identity
folder=tempfile.TemporaryDirectory();store=Store(Path(folder.name)/'browser.sqlite',seed=False)
app='checklist-browser';ready_production(store,app)
Access(store).bootstrap(app,identities.OWNER,{'confirm_owner':True})
service=Packaging(store);manifest=store.app(app)['version']
variant=service.save(app,dict(id='variant-one',version=0,kind='VARIANT',manifest_version=manifest,data=draft()))
segment=dict(id='opening',text='Show the original app step')
data=dict(variant=ref('VARIANT',variant),script=[segment],shots=[dict(id='opening-shot',segment_id='opening',segment_sha256=digest(segment),kind='SCREEN_RECORDING',description='Record the original app screen',source=None,start_ms=None,end_ms=None,assets=[],claims=[],claim_text='A claim needs authentic proof')])
service.save(app,dict(id='shots-one',version=0,kind='SHOTS',manifest_version=manifest,data=data))
server=Server(('127.0.0.1',0),store)
Path('.factory/content-packaging-t5/checklist-browser-state.json').write_bytes(json.dumps(dict(origin='http://127.0.0.1:'+str(server.server_port),app_id=app)).encode())
print('Synthetic checklist fixture listening on port '+str(server.server_port),flush=True)
try:server.serve_forever()
finally:server.server_close();folder.cleanup()
