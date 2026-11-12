"""Reject annotation removal from explicitly reviewed security boundaries."""

import ast
from pathlib import Path

FUNCTIONS = {
    "common.py": {
        "canonical",
        "digest",
        "now",
        "uid",
        "required",
        "amount",
        "fraction",
        "identifier",
        "safe_data",
        "iso_time",
    },
    "operation_catalog.py": {"descriptor", "catalog", "path_segment", "exact_keys", "request_data"},
    "campaign_contract.py": {
        "exact",
        "numeric",
        "whole",
        "hashes",
        "scope_acknowledgments",
        "scope_limits",
        "scope_data",
        "post_data",
        "reel_data",
        "target_countries",
        "ad_data",
    },
    "agent_grants.py": {"token_digest", "issue_data", "public", "app_scope", "current", "authenticated", "consume"},
    "review_access.py": {"member", "exact_role", "member_body"},
}


def check_source(source: str, names: set[str]) -> list[str]:
    """Check signatures, not annotation spelling or correctness (Pyright does that)."""
    functions = {
        node.name: node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    errors = []
    for name in sorted(names):
        node = functions.get(name)
        if node is None:
            errors.append(f"Missing reviewed function: {name}")
            continue
        parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        parameters.extend(arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
        for parameter in parameters:
            if parameter.annotation is None:
                errors.append(f"Missing parameter annotation: {name}.{parameter.arg}")
        if node.returns is None:
            errors.append(f"Missing return annotation: {name}")
    return errors


def check(root: Path) -> list[str]:
    """Fail if a named boundary loses annotations or the file disappears."""
    errors = []
    for name, functions in FUNCTIONS.items():
        path = root / "mission_control" / name
        if not path.is_file():
            errors.append(f"Missing danger-zone file: {name}")
            continue
        errors.extend(f"{name}: {error}" for error in check_source(path.read_text(encoding="utf-8"), functions))
    return errors
