"""Meaningful local source mutations; originals restored byte-for-byte after each run."""
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.factory/linux-studio-listener'
target=ROOT/'mission_control/studio_listener_linux.py'
cases=[
    ('socket-repeat',"if not live(first[1]) or diagnostic(port,deadline,budget)!=first_row:","if not live(first[1]):"),
    ('live-scope',"if allowed is not True:fail('SCOPE_REVOKED')","if False:fail('SCOPE_REVOKED')"),
    ('ambiguous',"if len(matches)!=1:return None","if not matches:return None"),
    ('truncation',"if flags or sender!=(0,0) or not raw:","if sender!=(0,0) or not raw:"),
    ('fd-budget',"if count>MAX_FDS or budget[0]>MAX_LINKS:","if budget[0]>MAX_LINKS:"),
    ('stable-witness',"if chosen is None and (preferred is None or pid==preferred):chosen=item","if chosen is None:chosen=item"),
    ('final-pidfd'," and live(first[1]) and live(second[1]) and first[0]", " and first[0]"),
    ('final-membership'," and first[0] in scope.members(deadline)", ""),
    ('post-validation-deadline',"self.validate();remaining(deadline);return values","self.validate();return values"),
    ('final-success-deadline',"remaining(deadline)\n    return result","return result"),
]
results=[]
for name,before,after in cases:
    original=target.read_bytes();text=original.decode()
    if text.count(before)!=1:raise RuntimeError('Mutation anchor not unique: '+name)
    try:
        target.write_text(text.replace(before,after),encoding='utf-8',newline='\n')
        result=subprocess.run([sys.executable,'-B','-m','unittest','tests.test_studio_listener_linux','-v'],cwd=ROOT,capture_output=True,text=True)
        (OUT/('mutation-'+name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8',newline='\n')
        killed=result.returncode!=0 and 'FAIL:' in result.stderr
        results.append(dict(name=name,killed=killed,exit_code=result.returncode))
    finally:target.write_bytes(original)
(OUT/'mutations.json').write_text(json.dumps(results,indent=2),encoding='utf-8',newline='\n')
print(json.dumps(results))
assert all(item['killed'] for item in results)
