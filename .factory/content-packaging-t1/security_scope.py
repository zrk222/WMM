"""Create exact-byte static scan scope of owned source and direct evidence dependencies."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.factory/content-packaging-t1/security-scope'
paths=['packaging_contract','packaging_bindings','packaging_store','db','common','pmf_contract',
       'funnel_store','creative_library','creative_briefs','discovery_store','managed_media_store']
manifest=[]
for name in paths:
    path='mission_control/'+name+'.py';source=ROOT/path;target=OUT/path
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    manifest.append(dict(path=path,sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
reads={
    'packaging_store':{'funnel_store.app_context':1,'packaging_bindings.resolve':2,
                       'packaging_bindings.variant_binding':2,'packaging_bindings.shot_claims':1},
    'packaging_bindings':{'creative_briefs.bound_record':1,'creative_library.latest_capture':1,
                          'discovery_store.latest':1,'funnel_store.creative_binding':2},
}
contract=dict(schema='factory.tenant-read-contract.v2',reads=[dict(path='mission_control/'+name+'.py',
    reads=[dict(call=call,binding=f'position:{index}:app_id') for call,index in calls.items()]) for name,calls in reads.items()])
(OUT/'.factory').mkdir(exist_ok=True)
shutil.copyfile(ROOT/'factory.database.json',OUT/'factory.database.json')
(OUT/'.factory/tenant-read-contract.json').write_text(json.dumps(contract,indent=2),encoding='utf-8')
(OUT/'scope-source-hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(ROOT/'.factory/content-packaging-t1/security-source-hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print('Prepared 11 exact-byte Python files, owned code plus direct evidence dependencies. Nested imports and other languages are outside this static scope.')
