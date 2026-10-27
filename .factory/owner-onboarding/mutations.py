"""Reject source sabotage that crosses app context or removes owner confirmation."""
from pathlib import Path
import json,shutil,subprocess,tempfile
P=Path('.factory/owner-onboarding');rows=[]
cases=[('app-scope','&&state.app===app&&\n    String','&&\n    String'),
       ('confirmation',"return api('/api/identity/login',{token});","await api('/api/identity/login',{token});return api(`/api/apps/${app}/access/bootstrap`,{confirm_owner:true});")]
for name,before,after in cases:
    with tempfile.TemporaryDirectory(prefix='wmm-owner-mutant-') as folder:
        root=Path(folder);(root/'tests').mkdir();(root/'mission_control/static').mkdir(parents=True)
        shutil.copy2('tests/owner_onboarding.test.cjs',root/'tests/owner_onboarding.test.cjs')
        source=Path('mission_control/static/verified-review.js');value=source.read_text(encoding='utf-8');assert value.count(before)==1
        (root/source).write_bytes(value.replace(before,after).encode('utf-8'))
        q=subprocess.run(['node','--test','tests/owner_onboarding.test.cjs'],cwd=root,capture_output=True)
        text=(q.stdout+q.stderr).decode('utf-8',errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(line.rstrip()for line in text.splitlines())+'\n').encode('utf-8'))
        assert q.returncode and 'not ok' in text,name
        rows.append(dict(name=name,status='KILLED',exit=q.returncode));print(name,'KILLED')
(P/'mutations.json').write_bytes((json.dumps(rows,indent=2)+'\n').encode('utf-8'))
