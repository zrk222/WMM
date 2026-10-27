"""Reject a false checklist response and a catalogue effect escalation."""
from pathlib import Path
import json,shutil,subprocess,tempfile
P=Path('.factory/content-packaging-t5/transport');rows=[]
cases=[('dispatch','packaging_access.py','return preview(store,app_id,body)','return dict(execution_authority=True)'),
       ('effect','operation_catalog.py',"'packaging.checklist':descriptor('POST','/packaging/checklist','READ_PRIVATE_LOCAL_DATA'","'packaging.checklist':descriptor('POST','/packaging/checklist','WRITE_LOCAL_PLAN'")]
for name,file,old,new in cases:
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        for directory in ['mission_control','tests']:shutil.copytree(directory,root/directory,ignore=shutil.ignore_patterns('__pycache__'))
        source=root/'mission_control'/file;s=source.read_text(encoding='utf-8');assert old in s;source.write_bytes(s.replace(old,new,1).encode())
        q=subprocess.run(['python','-m','unittest','tests.test_packaging_handoff_clients'],cwd=root,capture_output=True)
        s=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(x.rstrip() for x in s.splitlines())+'\n').encode())
        rows.append(dict(name=name,exit=q.returncode,status='KILLED' if q.returncode else 'SURVIVED'))
(P/'mutations.json').write_bytes(json.dumps(rows,indent=2).encode());print(rows);assert all(r['status']=='KILLED' for r in rows)
