"""Check that the growing maintained set stays formatted and lint-clean."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "tools/maintained_files.txt"
JS_LIST = ROOT / "tools/maintained_js.txt"


def maintained():
    return [
        line.strip()
        for line in LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and (ROOT / line.strip()).is_file()
    ]


def maintained_js():
    return [
        line.strip()
        for line in JS_LIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and (ROOT / line.strip()).is_file()
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
    scripts = maintained_js()
    missing_js = [path for path in scripts if not (ROOT / path).is_file()]
    if missing_js:
        print("MISSING " + " ".join(missing_js), file=sys.stderr)
        return 1
    if shutil.which("npx") is None or not (ROOT / "node_modules/prettier").exists():
        print("PRETTIER_REQUIRED run npm ci", file=sys.stderr)
        return 2
    prettier = subprocess.run(["npx", "--no-install", "prettier", "--check", *scripts], cwd=ROOT)
    if shutil.which("node") is None:
        print("NODE_REQUIRED install Node.js", file=sys.stderr)
        return 2
    syntax_ok = True
    for script in scripts:
        syntax = subprocess.run(["node", "--check", script], cwd=ROOT)
        syntax_ok = syntax.returncode == 0 and syntax_ok
    if not (ROOT / "node_modules/eslint").exists():
        print("ESLINT_REQUIRED run npm ci", file=sys.stderr)
        return 2
    eslint = subprocess.run(
        ["npx", "--no-install", "eslint", *scripts],
        cwd=ROOT,
    )
    module_graph = subprocess.run(["node", "tools/check_es_modules.mjs"], cwd=ROOT)
    return (
        0
        if formatted.returncode == 0
        and lint.returncode == 0
        and prettier.returncode == 0
        and syntax_ok
        and eslint.returncode == 0
        and module_graph.returncode == 0
        else 1
    )


def main():
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
