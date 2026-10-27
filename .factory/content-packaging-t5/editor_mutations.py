"""Bounded sabotage of the packaging-to-editor proof boundary."""
from pathlib import Path
import json,shutil,subprocess,tempfile
ROOT=Path.cwd();P=Path('.factory/content-packaging-t5/editor');rows=[]
mutants=[('taste','mission_control/packaging_editor.py',"if taste['version'] != value['taste']['version'] or taste['hash'] != value['taste']['sha256']:",'if False:'),
         ('origin','mission_control/packaging_editor.py',"if 'packaging' in before and 'packaging' not in after:",'if False:'),
         ('audio','mission_control/packaging_editor.py',"if 'audio' not in clip:",'if False:')]
for name,file,before,after in mutants:
    with tempfile.TemporaryDirectory(prefix='wmm-editor-mutant-')as directory:
        target=Path(directory)
        for folder in ['mission_control','tests']:
            shutil.copytree(ROOT/folder,target/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        path=target/file;value=path.read_text(encoding='utf-8');assert value.count(before)==1
        path.write_bytes(value.replace(before,after).encode('utf-8'))
        q=subprocess.run(['python','-m','unittest','tests.test_packaging_editor'],cwd=target,capture_output=True)
        log=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(line.rstrip()for line in log.splitlines())+'\n').encode('utf-8'))
        assert q.returncode and ('FAIL:'in log or 'ERROR:'in log),name
        rows.append(dict(name=name,status='KILLED',exit=q.returncode));print(name,'KILLED',flush=True)
(P/'mutations.json').write_bytes((json.dumps(rows,indent=2)+'\n').encode('utf-8'))
