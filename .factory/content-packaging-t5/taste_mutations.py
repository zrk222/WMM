"""Source sabotage runs only in disposable copies; never mutate the active app."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile

ROOT=Path.cwd();P=Path('.factory/content-packaging-t5/taste');results=[]
source='mission_control/creative_taste_store.py'
mutants=[('owner',source,"    context = PROTECTED.get()", "    return dict(principal='forged', role_version=1)\n    context = PROTECTED.get()"),
         ('app',source,"if data['manifest_version'] != app['version'] or data['app_hash'] != app['hash']:","if False:"),
         ('revision',source,"if (old['version'] if old else 0) != request['version']:","if False:"),
         ('immutable','mission_control/db.py',"CREATE TRIGGER IF NOT EXISTS taste_immutable_update BEFORE UPDATE ON creative_taste_reviews BEGIN SELECT RAISE(ABORT,'taste history is append-only'); END;",'')]
for name,file,before,after in mutants:
    with tempfile.TemporaryDirectory(prefix='wmm-taste-mutant-') as directory:
        target=Path(directory)
        for folder in ['mission_control','tests']:
            shutil.copytree(ROOT/folder,target/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        path=target/file;text=path.read_text(encoding='utf-8');assert text.count(before)==1
        path.write_text(text.replace(before,after),encoding='utf-8')
        q=subprocess.run(['python','-m','unittest','tests.test_creative_taste_store'],cwd=target,capture_output=True)
        text=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(line.rstrip() for line in text.splitlines())+'\n').encode('utf-8'))
        assert q.returncode!=0 and ('FAIL:' in text or 'ERROR:' in text),name
        results.append(dict(name=name,status='KILLED',exit=q.returncode));print(name,'KILLED',flush=True)
(P/'mutations.json').write_bytes((json.dumps(results,indent=2)+'\n').encode('utf-8'))
