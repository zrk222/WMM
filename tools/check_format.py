"""Check that the growing maintained set stays formatted and lint-clean."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "tools/maintained_files.txt"


def maintained():
    return [
        line.strip()
        for line in LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def check():
    if shutil.which("ruff") is None:
        print("RUFF_REQUIRED install docs/requirements-dev.txt", file=sys.stderr)
        return 2
    paths = maintained()
    missing = [path for path in paths if not (ROOT / path).is_file()]
    if missing:
        print("MISSING " + " ".join(missing), file=sys.stderr)
        return 1
    formatted = subprocess.run(["ruff", "format", "--check", *paths], cwd=ROOT)
    lint = subprocess.run(["ruff", "check", *paths], cwd=ROOT)
    return 0 if formatted.returncode == 0 and lint.returncode == 0 else 1


def main():
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
