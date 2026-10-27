"""Temporary source mutants must fail real checklist regressions."""
from pathlib import Path
import json,shutil,subprocess,tempfile
P=Path('.factory/content-packaging-t5/checklist');rows=[]
cases=[('identity',"if item['version']!=ref['version'] or item['hash']!=ref['sha256']:",'if False:'),
       ('rights',"if ref['kind']!='MEDIA':continue","if ref['kind']=='MEDIA':continue"),
       ('authority','execution_authority=False','execution_authority=True')]
for name,old,new in cases:
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for directory in ['mission_control','tests']:
            shutil.copytree(directory,root/directory,ignore=shutil.ignore_patterns('__pycache__'))
        source=root/'mission_control/packaging_handoff.py';s=source.read_text(encoding='utf-8');assert old in s
        source.write_bytes(s.replace(old,new,1).encode())
        q=subprocess.run(['python','-m','unittest','tests.test_packaging_handoff'],cwd=root,capture_output=True)
        output=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(x.rstrip() for x in output.splitlines())+'\n').encode())
        rows.append(dict(name=name,exit=q.returncode,status='KILLED' if q.returncode else 'SURVIVED'))
(P/'mutations.json').write_bytes(json.dumps(rows,indent=2).encode());print(rows)
assert all(r['status']=='KILLED' for r in rows)
