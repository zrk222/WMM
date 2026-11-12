"""Mechanical import-layering and operation-catalog coverage gates."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
STORAGE = {"db", "store"}
PORTABLE_FORBIDDEN = {
    "socket",
    "ssl",
    "urllib",
    "http",
    "subprocess",
    "sqlite3",
    "requests",
    "httpx",
    "playwright",
    "keyring",
    "os",
}


def modules() -> dict[str, Path]:
    return {path.stem: path for path in sorted(SOURCE.glob("*.py"))}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(
                node.module.split(".")[1] if node.module.startswith("mission_control.") else node.module.split(".")[0]
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(
                    alias.name.split(".")[1] if alias.name.startswith("mission_control.") else alias.name.split(".")[0]
                )
    return names


def graph() -> dict[str, list[str]]:
    known = modules()
    return {
        name: sorted(dependency for dependency in imports(path) if dependency in known) for name, path in known.items()
    }


def cycles(edges: dict[str, list[str]]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    stack: list[str] = []

    def visit(name: str) -> None:
        seen.add(name)
        stack.append(name)
        for dependency in edges.get(name, ()):
            if dependency in stack:
                found.append(" -> ".join(stack[stack.index(dependency) :] + [dependency]))
            elif dependency not in seen:
                visit(dependency)
        stack.pop()

    for name in edges:
        if name not in seen:
            visit(name)
    return found


def check(root: Path = ROOT) -> list[str]:
    known = modules()
    raw = {name: imports(path) for name, path in known.items()}
    edges = {
        name: sorted(dependency for dependency in dependencies if dependency in known)
        for name, dependencies in raw.items()
    }
    findings = ["import cycle: " + cycle for cycle in cycles(edges)]
    for name, dependencies in raw.items():
        if name in STORAGE or name.endswith("_store"):
            findings.extend(
                f"storage module {name} imports {dependency}"
                for dependency in dependencies
                if dependency in ("service", "server") or dependency.endswith("_http")
            )
        if name.endswith("_portable"):
            findings.extend(
                f"portable module {name} imports {dependency}"
                for dependency in dependencies
                if dependency in PORTABLE_FORBIDDEN
            )
    from .operation_catalog import OPERATIONS

    corpus = "\n".join(
        path.read_text(encoding="utf-8-sig", errors="ignore") for path in (Path(root) / "tests").glob("test_*.py")
    )
    documentation = Path(root) / "docs/operation-catalog.md"
    rows = documentation.read_text(encoding="utf-8") if documentation.exists() else ""
    findings.extend(f"operation {name} has no test reference" for name in sorted(OPERATIONS) if name not in corpus)
    findings.extend(f"operation {name} has no docs row" for name in sorted(OPERATIONS) if name not in rows)
    return findings


def main() -> int:
    findings = check()
    print(
        "ARCHITECTURE_GATE "
        + json.dumps(dict(schema="wmm.architecture-gate.v1", ok=not findings, findings=findings), sort_keys=True)
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
