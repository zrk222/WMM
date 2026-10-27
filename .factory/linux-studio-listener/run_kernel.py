"""Run only existing-image offline experiments against a read-only source mount."""
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
argv=['docker','run','--rm','--network','none','--mount',f'type=bind,source={ROOT},target=/workspace,readonly',
      '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/workspace','-w','/workspace','--entrypoint','python3',
      'wmm-ubuntu-workflows:local','/workspace/.factory/linux-studio-listener/kernel_component.py']
result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
(ROOT/'.factory/linux-studio-listener/kernel-component.log').write_text(result.stdout+result.stderr,encoding='utf-8',newline='\n')
print(result.stdout+result.stderr)
raise SystemExit(result.returncode)
