"""Deterministic design gates on actual synthetic dialog DOM; captures stay private."""
from pathlib import Path
import json,subprocess
P=Path('.factory/content-packaging-taste-ui');target=P/'rendered-modal.html'
commands=[('design-audit',['prestige','audit',str(target),'--json']),
          ('critique',['prestige','critique',str(target),'--challenge','--strict','--out',str(P/'critique.json')]),
          ('challenge',['prestige','challenge',str(target),'--workflow','product','--out',str(P/'challenge.json')]),
          ('render-audit',['prestige','render-audit',str(target),'--out-dir',str(P/'render'),'--json'])]
for name,args in commands:
    q=subprocess.run(args,capture_output=True)
    if name in ['critique','challenge']:data=json.loads((P/(name+'.json')).read_bytes())
    else:
        data=json.loads(q.stdout)
        (P/(name+'.json')).write_bytes((json.dumps(data,indent=2)+'\n').encode('utf-8'))
    print(name,q.returncode,data.get('passed'),flush=True)
    assert q.returncode==0 and data['passed'],name
