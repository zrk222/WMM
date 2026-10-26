"""Run semantic mutants in temporary copies, never in the working source."""
from pathlib import Path
import json,shutil,subprocess,tempfile
P=Path('.factory/content-packaging-t4');rows=[]
cases=[('authority','packaging-ui.js',"r.role==='OWNER'","true"),
       ('scope','packaging-ui.js','active===t&&t.node.open&&m.equal(t.scope,scope(t.d.state))','active===t&&t.node.open'),
       ('canonical-hash','packaging-model.js',"stable(value)","JSON.stringify(value)")]
for name,file,old,new in cases:
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);(root/'tests').mkdir();(root/'mission_control/static').mkdir(parents=True)
        for test in ['packaging_model.test.cjs','packaging_ui.test.cjs']:shutil.copy2('tests/'+test,root/'tests'/test)
        for source in ['packaging-model.js','packaging-ui.js']:shutil.copy2('mission_control/static/'+source,root/'mission_control/static'/source)
        path=root/'mission_control/static'/file;s=path.read_text(encoding='utf-8');assert old in s,(name,old)
        path.write_bytes(s.replace(old,new,1).encode())
        q=subprocess.run(['node','--test','tests/packaging_model.test.cjs','tests/packaging_ui.test.cjs'],cwd=root,capture_output=True)
        output=(q.stdout+q.stderr).decode('utf-8',errors='replace')
        for prefix in [str(Path.home()),Path.home().as_posix()]:output=output.replace(prefix,'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes((chr(10).join(line.rstrip() for line in output.splitlines())+chr(10)).encode())
        rows.append(dict(name=name,status='KILLED' if q.returncode else 'SURVIVED',exit=q.returncode))
(P/'mutations.json').write_bytes(json.dumps(rows,indent=2).encode());print(rows)
assert all(r['status']=='KILLED' for r in rows)
