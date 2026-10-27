"""Expose exact UMD factory functions for Forge's exported-symbol metrics."""
from pathlib import Path
import hashlib,json,re,subprocess
P=Path('.factory/content-packaging-t4');S=P/'qa-scope';S.mkdir(exist_ok=True)
bindings=[];modules=[]
for name in ['packaging-model','packaging-ui']:
    source=Path('mission_control/static/'+name+'.js');raw=source.read_bytes()
    lines=raw.decode('utf-8').splitlines(keepends=True)
    assert lines[1].startswith('(function(') and lines[-1].strip()=='});' and lines[-2].startswith('return {')
    body=''.join(lines[2:-2])
    extracted=re.sub(r'(?m)^((?:async )?function )',r'export \1',body)
    assert re.sub(r'(?m)^export ((?:async )?function )',r'\1',extracted)==body
    target=S/(name+'.js');target.write_bytes(extracted.encode())
    bindings.append(dict(source=source.as_posix(),sha256=hashlib.sha256(raw).hexdigest(),extracted=target.as_posix(),extracted_sha256=hashlib.sha256(extracted.encode()).hexdigest(),method='UMD factory body, export keyword added solely for public-function metric visibility; bodies unchanged'))
    modules.append(dict(name=name.replace('-','_'),path=target.as_posix(),language='javascript',functions=[dict(name=m[0],args=[],returns='object') for m in re.findall(r'(?:async )?function (\w+)\(([^)]*)\)',body)]))
(P/'qa-source-bindings.json').write_bytes(json.dumps(bindings,indent=2).encode())
Path('specs/content-packaging-t4.ssat.yaml').write_bytes(json.dumps(dict(name='content-packaging-t4',language='javascript',modules=modules),indent=2).encode())
q=subprocess.run(['forge','qa','content-packaging-t4','--ssat','specs/content-packaging-t4.ssat.yaml','--strict'],capture_output=True)
(P/'qa.json').write_bytes(q.stdout);(P/'qa-stderr.log').write_bytes(q.stderr)
d=json.loads(q.stdout);print(dict(exit=q.returncode,grade=d['grade'],passed=d['passed'],max_complexity=d['metrics']['max_complexity'],findings=d['findings']))
raise SystemExit(q.returncode)
