"""Mutants for cross-app receipt admission and late response presentation."""
from pathlib import Path
import json,shutil,subprocess,tempfile
P=Path('.factory/content-packaging-taste-ui');rows=[]
cases=[('receipt','packaging-model.js',"value?.app_id!==app","false"),
       ('late-response','packaging-ui.js',"if(!current(t))return;m.tasteReceipt(saved","m.tasteReceipt(saved")]
for name,file,old,new in cases:
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);(root/'tests').mkdir();(root/'mission_control/static').mkdir(parents=True)
        for n in ['packaging_model.test.cjs','packaging_ui.test.cjs']:shutil.copy2('tests/'+n,root/'tests'/n)
        for n in ['packaging-model.js','packaging-ui.js']:shutil.copy2('mission_control/static/'+n,root/'mission_control/static'/n)
        f=root/'mission_control/static'/file;s=f.read_text(encoding='utf-8');assert old in s;f.write_bytes(s.replace(old,new,1).encode())
        q=subprocess.run(['node','--test','tests/packaging_model.test.cjs','tests/packaging_ui.test.cjs'],cwd=root,capture_output=True)
        s=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(x.rstrip() for x in s.splitlines())+'\n').encode())
        rows.append(dict(name=name,exit=q.returncode,status='KILLED' if q.returncode else 'SURVIVED'))
(P/'mutations.json').write_bytes(json.dumps(rows,indent=2).encode());print(rows);assert all(r['status']=='KILLED' for r in rows)
