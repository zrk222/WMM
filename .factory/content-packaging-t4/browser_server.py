"""Isolated synthetic browser fixture; no external identity or production data."""
from pathlib import Path
import json,tempfile
from mission_control.store import Store
from mission_control.server import Server
from mission_control.creative_library import Library
from mission_control import operator_identity
from tests.test_creative_production import ready_production
from tests.test_creative_library import reference
from tests import test_verified_review as identities

operator_identity.github_read=identities.synthetic_identity
folder=tempfile.TemporaryDirectory()
store=Store(Path(folder.name)/'browser.sqlite',seed=False)
app='packaging-browser'
ready_production(store,app)
Library(store).save(app,dict(data=reference(title='Show the app task in three steps',post_id='reference-two',creator_id='creator-two')))
Library(store).save(app,dict(data=reference(title='An original opening worth comparing',post_id='reference-three',creator_id='creator-three')))
server=Server(('127.0.0.1',0),store)
Path('.factory/content-packaging-t4/browser-state.json').write_bytes(json.dumps(dict(origin='http://127.0.0.1:'+str(server.server_port),app_id=app)).encode())
print('Synthetic browser fixture listening on port '+str(server.server_port),flush=True)
try:server.serve_forever()
finally:server.server_close();folder.cleanup()
