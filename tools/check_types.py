"""Type-check the growing maintained Python allowlist with pinned Pyright."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "tools/maintained_files.txt"
GENERATED = "mission_control/schema_types.py"


def maintained():
    return [
        line.strip()
        for line in LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and (ROOT / line.strip()).is_file()
    ]


def python_files():
    return [path for path in maintained() if path.endswith(".py")] + [GENERATED]


def check():
    spec = importlib.util.spec_from_file_location("danger_zone_types", ROOT / "tools/danger_zone_types.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Danger-zone annotation checker is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors = module.check(ROOT)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if shutil.which("npx") is None or not (ROOT / "node_modules/pyright").exists():
        print("PYRIGHT_REQUIRED run npm ci", file=sys.stderr)
        return 2
    result = subprocess.run(["npx", "--no-install", "pyright", "--pythonversion", "3.11", *python_files()], cwd=ROOT)
    return 0 if result.returncode == 0 else 1


def main():
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
