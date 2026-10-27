"""Run negative controls against isolated synthetic source copies."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path.cwd().resolve()
OUT = ROOT / '.factory/apple-analytics-parser'
source = (ROOT / 'mission_control/apple_analytics_parser.py').read_text(encoding='utf-8')
tests = (ROOT / 'tests/test_apple_analytics_parser.py').read_text(encoding='utf-8')
mutations = {
    'baseline': None,
    'checksum': ("if hashlib.md5(raw, usedforsecurity=False).hexdigest() != checksum.lower():", 'if False:'),
    'foreign_app': ("if row['app apple identifier'] != app_id:", 'if False:'),
    'correction': ('processing > previous[0]', 'processing < previous[0]'),
}
results = {}
with tempfile.TemporaryDirectory(prefix='wmm-parser-mutants-') as folder:
    path = Path(folder)
    (path / 'mission_control').mkdir()
    (path / 'tests').mkdir()
    (path / 'mission_control/__init__.py').write_text("from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n", encoding='utf-8')
    (path / 'tests/__init__.py').write_text('', encoding='utf-8')
    (path / 'tests/test_apple_analytics_parser.py').write_text(tests, encoding='utf-8')
    for name, mutation in mutations.items():
        if mutation and source.count(mutation[0]) != 1:
            raise RuntimeError('mutation target changed: ' + name)
        candidate = source.replace(*mutation) if mutation else source
        (path / 'mission_control/apple_analytics_parser.py').write_text(candidate, encoding='utf-8')
        env = dict(os.environ, PYTHONPATH=str(path) + os.pathsep + str(ROOT), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        run = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'tests.test_apple_analytics_parser', '-v'], cwd=path, env=env, capture_output=True, text=True, timeout=60)
        safe = (run.stdout + run.stderr).replace(str(path), '<temporary>').replace(str(Path.home()), '<home>')
        normalized = '\n'.join(line.rstrip() for line in safe.splitlines()) + '\n'
        (OUT / ('mutation-' + name + '.log')).write_text(normalized, encoding='utf-8', newline='\n')
        results[name] = run.returncode
        if (name == 'baseline' and run.returncode != 0) or (name != 'baseline' and run.returncode == 0):
            raise RuntimeError('mutation test failed: ' + name)
(OUT / 'mutations.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8', newline='\n')
print('Baseline passed; 3 mutations killed.')
