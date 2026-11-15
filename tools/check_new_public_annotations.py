"""Reject new public functions in enrolled Python files without complete annotations."""

import argparse
import ast
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def maintained(root: Path) -> set[str]:
    """Read the Python files that already own formatting and type coverage."""
    path = root / "tools/maintained_files.txt"
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#") and line.strip().endswith(".py")
    }


def public_functions(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Return top-level and public class functions keyed by stable qualified names."""
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            found[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not item.name.startswith("_") or item.name == "__init__"
                ):
                    found[f"{node.name}.{item.name}"] = item
    return found


def missing_annotations(name: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Require every parameter and the return value, skipping only an instance receiver."""
    positional = [*node.args.posonlyargs, *node.args.args]
    if (
        positional
        and positional[0].arg in {"self", "cls"}
        and not any(isinstance(item, ast.Name) and item.id == "staticmethod" for item in node.decorator_list)
    ):
        positional = positional[1:]
    parameters = [*positional, *node.args.kwonlyargs]
    parameters.extend(arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
    errors = [f"Missing parameter annotation: {name}.{item.arg}" for item in parameters if item.annotation is None]
    if node.returns is None:
        errors.append(f"Missing return annotation: {name}")
    return errors


def check_sources(path: str, before: str, after: str) -> list[str]:
    """Fail for new public functions and annotations removed from complete ones."""
    old = public_functions(before)
    new = public_functions(after)
    errors = [
        f"{path}: {error}" for name in sorted(set(new) - set(old)) for error in missing_annotations(name, new[name])
    ]
    for name in sorted(set(new) & set(old)):
        if not missing_annotations(name, old[name]) and missing_annotations(name, new[name]):
            errors.extend(f"{path}: {error}" for error in missing_annotations(name, new[name]))
    return errors


def git(root: Path, *args: str) -> bytes:
    """Run one read-only Git command."""
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def source(root: Path, revision: str, path: str) -> str:
    """Read a file at a revision, treating absence as an empty baseline."""
    try:
        return git(root, "show", f"{revision}:{path}").decode("utf-8")
    except subprocess.CalledProcessError:
        return ""


def changed(root: Path, base: str, head: str, paths: set[str]) -> set[str]:
    """List added or modified Python files that are already enrolled."""
    names = git(root, "diff", "--name-only", "-z", "--diff-filter=AMR", base, head).decode("utf-8").split("\0")
    return {name for name in names if name in paths}


def audit(root: Path, base: str, head: str) -> dict[str, object]:
    """Return every annotation gap on newly introduced public functions."""
    paths = maintained(root)
    errors: list[str] = []
    for path in sorted(changed(root, base, head, paths)):
        candidate = root / path
        if not candidate.is_file():
            continue
        errors.extend(check_sources(path, source(root, base, path), candidate.read_text(encoding="utf-8")))
    return {"schema": "wmm.new-public-annotations.v1", "ok": not errors, "errors": errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = audit(args.root.resolve(), args.base, args.head)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
