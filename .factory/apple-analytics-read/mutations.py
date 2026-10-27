"""Challenge current tests against disposable module copies; never edit the checkout."""
from pathlib import Path
import json
import subprocess
import tempfile

ROOT=Path.cwd(); P=ROOT/'.factory/apple-analytics-read'
source=(ROOT/'mission_control/apple_analytics.py').read_text()
mutations={
    'foreign-parent':("if linked is not None and linked != {'type': kind, 'id': key}:", 'if False:'),
    'foreign-host':("parsed.netloc != 'api.appstoreconnect.apple.com'", 'False'),
    'unknown-metrics':('metric_observations=None', 'metric_observations=0')}
results=[]
with tempfile.TemporaryDirectory(prefix='wmm-analytics-mutation-') as directory:
    work=Path(directory); (work/'mission_control').mkdir(); (work/'tests').mkdir()
    (work/'mission_control/__init__.py').write_text('__path__.append('+repr(str(ROOT/'mission_control'))+')\n')
    (work/'tests/__init__.py').write_text('')
    (work/'tests/test_apple_analytics.py').write_bytes((ROOT/'tests/test_apple_analytics.py').read_bytes())
    target=work/'mission_control/apple_analytics.py'
    for name,change in [('baseline',None),*mutations.items()]:
        text=source if change is None else source.replace(*change)
        assert change is None or text!=source
        target.write_bytes(text.encode())
        # Avoid stale .pyc reuse between same-length disposable mutations.
        cache=work/'mission_control/__pycache__'
        if cache.exists():
            for entry in cache.glob('apple_analytics.*.pyc'): entry.unlink()
        result=subprocess.run(['python','-B','-m','unittest','tests.test_apple_analytics','-v'],cwd=work,capture_output=True)
        log=(result.stdout+result.stderr).decode(errors='replace').replace(str(Path.home()),'<LOCAL_PROFILE>')
        (P/('mutation-'+name+'.log')).write_bytes(('\n'.join(line.rstrip() for line in log.splitlines())+'\n').encode())
        killed=result.returncode!=0
        assert not killed if name=='baseline' else killed,name
        results.append(dict(name=name,status='PASS' if name=='baseline' else 'KILLED'))
(P/'mutations.json').write_bytes((json.dumps(results,indent=2)+'\n').encode())
print(json.dumps(results))
