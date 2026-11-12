"""Enroll changed source and reject missing enrollment or shrinking registries."""

import argparse
import json
import subprocess
from pathlib import Path

REGISTRIES = {
    ".py": "tools/maintained_files.txt",
    ".js": "tools/maintained_js.txt",
    ".mjs": "tools/maintained_js.txt",
    ".cjs": "tools/maintained_js.txt",
}


def git(root: Path, *args: str) -> bytes:
    """Read Git data without evaluating repository content or shell arguments."""
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def paths(text: str) -> set[str]:
    """Read a comment-bearing, line-oriented registry."""
    return {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}


def changed(root: Path, base: str, head: str | None) -> set[str]:
    """Compare the exact base to HEAD or the local index/working tree."""
    git(root, "rev-parse", "--verify", base + "^{commit}")
    git(root, "merge-base", "--is-ancestor", base, head or "HEAD")
    args = ["diff", "--name-only", "-z", "--diff-filter=ACMRT", base]
    if head:
        args.append(head)
    names = set(git(root, *args, "--").decode().split("\0")) - {""}
    if not head:
        names.update(set(git(root, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")) - {""})
    if any("\n" in name or "\r" in name for name in names):
        raise ValueError("Source paths must fit one registry line")
    return names


def audit(root: Path, base: str, head: str | None = None, *, write: bool = False) -> dict[str, object]:
    """Fail closed on unregistered source; enrollment never removes history."""
    if write and head:
        raise ValueError("Enrollment writes only the local working tree")
    touched = changed(root, base, head)
    errors: list[str] = []
    enrolled: list[str] = []
    for registry in sorted(set(REGISTRIES.values())):
        previous = paths(git(root, "show", f"{base}:{registry}").decode())
        current_text = git(root, "show", f"{head}:{registry}").decode() if head else (root / registry).read_text()
        current = paths(current_text)
        removed = previous - current
        errors.extend(f"Registry history removed: {registry}: {name}" for name in sorted(removed))
        required = {name for name in touched if REGISTRIES.get(Path(name).suffix) == registry}
        missing = required - current
        if write:
            current |= previous | required
            (root / registry).write_text(
                "# Automatically enrolled source; entries only grow.\n" + "\n".join(sorted(current)) + "\n"
            )
            enrolled.extend(sorted(missing))
            errors = [error for error in errors if not error.startswith(f"Registry history removed: {registry}:")]
        else:
            errors.extend(f"Enroll changed source: {registry}: {name}" for name in sorted(missing))
        for name in current - previous:
            if head:
                rows = git(root, "ls-tree", "--full-tree", "-z", head, "--", name).decode().split("\0")
                candidate = any(
                    row.startswith(("100644 blob ", "100755 blob ")) and row.split("\t", 1)[-1] == name for row in rows
                )
            else:
                candidate = (root / name).is_file() and not (root / name).is_symlink()
            if not candidate:
                errors.append(f"New registry path is absent: {name}")
    return {"schema": "wmm.source-ratchet.v1", "ok": not errors, "errors": errors, "enrolled": enrolled}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = audit(args.root.resolve(), args.base, args.head, write=args.write)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
