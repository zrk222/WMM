"""Prove agent taste dispatch and read-effect contract reject sabotage."""
from pathlib import Path
import json,shutil,subprocess,tempfile
ROOT=Path.cwd();P=Path('.factory/content-packaging-t5/taste-agent');rows=[]
mutants=[('dispatch','mission_control/creative_taste_store.py',"'taste-read': read", "'taste-read': save"),
         ('effect','mission_control/operation_catalog.py',"'packaging.taste-read':descriptor('POST','/packaging/taste-read','READ_PRIVATE_LOCAL_DATA'", "'packaging.taste-read':descriptor('POST','/packaging/taste-read','WRITE_LOCAL_PLAN'")]
for name,file,before,after in mutants:
    with tempfile.TemporaryDirectory(prefix='wmm-taste-client-mutant-') as folder:
        target=Path(folder)
        for module in ['mission_control','tests']:
            shutil.copytree(ROOT/module,target/module,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        path=target/file;content=path.read_text(encoding='utf-8');assert content.count(before)==1
        path.write_bytes(content.replace(before,after).encode('utf-8'))
        q=subprocess.run(['python','-m','unittest','tests.test_creative_taste_clients'],cwd=target,capture_output=True)
        log=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(line.rstrip() for line in log.splitlines())+'\n').encode('utf-8'))
        assert q.returncode and ('FAIL:' in log or 'ERROR:' in log)
        rows.append(dict(name=name,status='KILLED',exit=q.returncode));print(name,'KILLED',flush=True)
(P/'mutations.json').write_bytes((json.dumps(rows,indent=2)+'\n').encode('utf-8'))
