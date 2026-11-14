"""Reject annotation removal from explicitly reviewed security boundaries."""

import ast
from pathlib import Path

PUBLIC_CLASSES = {"review_access.py": {"Access"}}

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
    "campaign_schedule_authority.py": {
        "bound",
        "check",
        "check_lease",
        "check_content",
        "check_scope",
        "check_deadline",
        "video_context",
        "video_content",
        "video_deadline",
    },
    "agent_grants.py": {"token_digest", "issue_data", "public", "app_scope", "current", "authenticated", "consume"},
    "review_access.py": {"member", "exact_role", "member_body"},
}


def check_source(source: str, names: set[str], public_classes: set[str] | None = None) -> list[str]:
    """Check signatures, not annotation spelling or correctness (Pyright does that)."""
    top = ast.parse(source).body
    functions = {node.name: node for node in top if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    errors: list[str] = []
    if public_classes:
        names = names | {name for name in functions if not name.startswith("_")}
    for class_name in sorted(public_classes or ()):
        owner = next((node for node in top if isinstance(node, ast.ClassDef) and node.name == class_name), None)
        if owner is None:
            errors.append(f"Missing reviewed class: {class_name}")
            continue
        errors.extend(
            problem
            for node in owner.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (not node.name.startswith("_") or node.name == "__init__")
            for problem in check_signature(f"{class_name}.{node.name}", node, skip_receiver=True)
        )
    for name in sorted(names):
        node = functions.get(name)
        if node is None:
            errors.append(f"Missing reviewed function: {name}")
            continue
        errors.extend(check_signature(name, node))
    return errors


def check_signature(
    name: str, node: ast.FunctionDef | ast.AsyncFunctionDef, *, skip_receiver: bool = False
) -> list[str]:
    positional = [*node.args.posonlyargs, *node.args.args]
    if (
        skip_receiver
        and positional
        and positional[0].arg in {"self", "cls"}
        and not any(isinstance(item, ast.Name) and item.id == "staticmethod" for item in node.decorator_list)
    ):
        positional = positional[1:]
    parameters = [*positional, *node.args.kwonlyargs]
    parameters.extend(arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None)
    errors = [f"Missing parameter annotation: {name}.{param.arg}" for param in parameters if param.annotation is None]
    if node.returns is None:
        errors.append(f"Missing return annotation: {name}")
    return errors


def check(root: Path) -> list[str]:
    """Fail if a named boundary loses annotations or the file disappears."""
    errors: list[str] = []
    for name, functions in FUNCTIONS.items():
        path = root / "mission_control" / name
        if not path.is_file():
            errors.append(f"Missing danger-zone file: {name}")
            continue
        errors.extend(
            f"{name}: {error}"
            for error in check_source(path.read_text(encoding="utf-8"), functions, PUBLIC_CLASSES.get(name))
        )
    return errors
