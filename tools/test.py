"""Canonical, profile-aware test entry point.

Examples:
  python tools/test.py --profile inventory
  python tools/test.py --profile core --install
  python tools/test.py --profile browser --install
  python tools/test.py --profile node
  python tools/test.py --profile all

The core profile mirrors CI: hash-pinned runtime requirements, MCP/auth test
packages, FFmpeg and a platform keyring. Browser adds Playwright. Profiles are
reported before any test runs so a clean checkout cannot silently look green
with optional coverage missing.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PROFILES = ("inventory", "core", "browser", "node", "all")
CORE_REQUIREMENTS = ("requirements.txt", "docs/requirements-mcp.txt", "docs/requirements-auth.txt")
BROWSER_REQUIREMENTS = CORE_REQUIREMENTS + ("docs/requirements-browser.txt",)


def have_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def core_gaps() -> list[str]:
    gaps = []
    if sys.version_info < (3, 11):
        gaps.append("Python 3.11 or newer is required")
    if not have_module("zoneinfo"):
        gaps.append("Python zoneinfo support is required")
    for module, label in (
        ("mcp", "MCP test package (docs/requirements-mcp.txt)"),
        ("keyring", "keyring package needed by platform credential tests"),
    ):
        if not have_module(module):
            gaps.append(label)
    if shutil.which("ffmpeg") is None:
        gaps.append("FFmpeg is not on PATH (media/native test profile)")
    return gaps


def browser_gaps() -> list[str]:
    gaps = []
    if not have_module("playwright"):
        gaps.append("Playwright is not installed (docs/requirements-browser.txt)")
    if shutil.which("ffmpeg") is None:
        gaps.append("FFmpeg is not on PATH")
    return gaps


def node_gaps() -> list[str]:
    return [] if shutil.which("node") else ["Node.js is not on PATH"]


def install(profile: str) -> None:
    files = BROWSER_REQUIREMENTS if profile in ("browser", "all") else CORE_REQUIREMENTS
    for name in files:
        path = ROOT / name
        if not path.exists():
            raise SystemExit("Declared requirements file is missing: " + name)
        command = [sys.executable, "-m", "pip", "install"]
        if name == "requirements.txt":
            command.append("--require-hashes")
        command += ["--only-binary=:all:", "-r", str(path)]
        print("INSTALL " + " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
    if profile in ("browser", "all") and have_module("playwright"):
        command = [sys.executable, "-m", "playwright", "install", "chromium"]
        print("INSTALL " + " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)


def is_browser_module(name: str) -> bool:
    lowered = name.lower()
    return "browser" in lowered


def discover(profile: str) -> tuple[list, int]:
    """Return selected tests and the count of excluded browser modules."""
    suite = unittest.TestLoader().discover(start_dir=str(ROOT / "tests"), pattern="test_*.py")
    cases = list(flatten(suite))
    if profile in ("core", "all"):
        return cases, 0
    selected = []
    excluded = 0
    for case in cases:
        module = type(case).__module__
        if is_browser_module(module):
            excluded += 1
            continue
        selected.append(case)
    return selected, excluded


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        elif isinstance(item, unittest.TestCase):
            yield item
        else:
            raise ValueError("Discovery returned a non-TestCase leaf")


def node_tests() -> int:
    files = sorted((ROOT / "tests").glob("*.test.cjs"))
    files += sorted((ROOT / "tests").glob("*.test.mjs"))
    if not files:
        raise SystemExit("No Node test files found")
    print(f"NODE {len(files)} files", flush=True)
    result = subprocess.run(["node", "--test", *(str(path) for path in files)], cwd=ROOT)
    return result.returncode


def report(profile: str, gaps: list[str], selected: int, excluded: int) -> None:
    print(f"PROFILE {profile}", flush=True)
    print(f"SELECTED {selected} python tests; EXCLUDED {excluded} browser tests", flush=True)
    if gaps:
        print("PROFILE GAPS:", flush=True)
        for gap in gaps:
            print("  - " + gap, flush=True)
        print("Use --install for Python profiles; install OS tools from docs/TESTING.md.", flush=True)
    else:
        print("PROFILE PREREQUISITES: present", flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=PROFILES, default="core")
    parser.add_argument("--install", action="store_true", help="Install declared pip profile before testing")
    parser.add_argument(
        "--allow-missing", action="store_true", help="Run and report skips even when profile tools are absent"
    )
    parser.add_argument("--list", action="store_true", help="List profiles and expected suites without running")
    args = parser.parse_args(argv)
    if args.list or args.profile == "inventory":
        print("PROFILES", flush=True)
        print("  inventory  no tests; reports the declared profile surface", flush=True)
        print(
            "  core       Python suites with CI-equivalent optional packages; browser modules skip without Playwright",
            flush=True,
        )
        print("  browser    Browser unittest modules; requires Playwright and FFmpeg", flush=True)
        print("  node       Node browser-logic suites; requires Node.js", flush=True)
        print("  all        core + browser + node", flush=True)
        return 0
    if args.install:
        install(args.profile)
    gaps = []
    if args.profile in ("core", "all"):
        gaps += core_gaps()
    if args.profile in ("browser", "all"):
        gaps += browser_gaps()
    if args.profile in ("node", "all"):
        gaps += node_gaps()
    if gaps and not args.allow_missing:
        report(args.profile, gaps, 0, 0)
        return 2
    status = 0
    if args.profile in ("browser", "all"):
        os.environ.setdefault("WMM_BROWSER_TEST_PROFILE", "1")
    if args.profile in ("core", "browser", "all"):
        if args.profile == "browser":
            modules = [path for path in sorted((ROOT / "tests").glob("test_*.py")) if "browser" in path.name.lower()]
            if not modules:
                raise SystemExit("No browser unittest modules found")
            suite = unittest.TestLoader().discover(start_dir=str(ROOT / "tests"), pattern="test_*browser*.py")
            cases = list(flatten(suite))
        else:
            cases, _ = discover(args.profile)
        report(args.profile, gaps, len(cases), 0 if args.profile != "core" else 0)
        result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(cases))
        print(
            f"SUMMARY profile={args.profile} ran={result.testsRun} "
            f"failures={len(result.failures)} errors={len(result.errors)} skipped={len(result.skipped)}",
            flush=True,
        )
        if result.failures:
            print("FAILURES:", flush=True)
            for case, _ in result.failures:
                print("  - " + case.id(), flush=True)
        if result.errors:
            print("ERRORS:", flush=True)
            for case, _ in result.errors:
                print("  - " + case.id(), flush=True)
        if not result.wasSuccessful():
            status = 1
    if args.profile in ("node", "all"):
        if not node_gaps() or args.allow_missing:
            status = node_tests() or status
    return status


if __name__ == "__main__":
    raise SystemExit(main())
