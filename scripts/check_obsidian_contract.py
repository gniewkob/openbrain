#!/usr/bin/env python3
"""Guardrail: enforce Obsidian tool gating and capabilities contract invariants."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "unified/contracts/capabilities_manifest.json"
DISABLED_REASON_CONTRACT = ROOT / "unified/contracts/obsidian_disabled_reason_contract.json"
GATEWAY_MAIN = ROOT / "unified/mcp-gateway/src/main.py"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
HTTP_TRANSPORT_UTILS = ROOT / "unified/src/mcp_transport_utils.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _check_manifest() -> list[str]:
    errors: list[str] = []
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    http_tools = payload.get("http_obsidian_tools", [])
    local_tools = payload.get("local_obsidian_tools", [])
    if not isinstance(http_tools, list) or not http_tools:
        errors.append("capabilities_manifest http_obsidian_tools must be a non-empty list")
    if not isinstance(local_tools, list) or not local_tools:
        errors.append("capabilities_manifest local_obsidian_tools must be a non-empty list")
    missing = [tool for tool in http_tools if tool not in local_tools]
    if missing:
        errors.append(f"http_obsidian_tools must be subset of local_obsidian_tools: missing={missing}")
    return errors


def _find_async_function(tree: ast.AST, function_name: str) -> ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            return node
    return None


def _find_function(tree: ast.AST, function_name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    return None


def _function_calls_name(func: ast.AsyncFunctionDef, call_name: str) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == call_name:
            return True
    return False


def _sync_function_calls_name(func: ast.FunctionDef, call_name: str) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == call_name:
            return True
    return False


def _http_obsidian_tools_defined_under_flag(text: str, tool_names: list[str]) -> bool:
    tree = ast.parse(text)
    required_defs = {f"brain_{name}" for name in tool_names}
    found_defs: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        cond = node.test
        if not (isinstance(cond, ast.Name) and cond.id == "ENABLE_HTTP_OBSIDIAN_TOOLS"):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AsyncFunctionDef):
                if stmt.name in required_defs:
                    found_defs.add(stmt.name)
    return found_defs == required_defs


def _check_gateway_gating() -> list[str]:
    errors: list[str] = []
    text = GATEWAY_MAIN.read_text(encoding="utf-8")
    tree = ast.parse(text)
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    local_tools = payload.get("local_obsidian_tools", [])

    if 'OBSIDIAN_LOCAL_TOOLS_ENV = "ENABLE_LOCAL_OBSIDIAN_TOOLS"' not in text:
        errors.append("gateway must define ENABLE_LOCAL_OBSIDIAN_TOOLS env constant")
    if "_require_obsidian_local_tools_enabled" not in text:
        errors.append("gateway must guard local obsidian tools with _require_obsidian_local_tools_enabled")
    for tool in local_tools:
        fn_name = f"brain_{tool}"
        fn = _find_async_function(tree, fn_name)
        if fn is None:
            errors.append(f"missing function: {fn_name}")
            continue
        if not _function_calls_name(fn, "_require_obsidian_local_tools_enabled"):
            errors.append(f"{fn_name} must call _require_obsidian_local_tools_enabled()")

    required_caps = (
        '"obsidian": {',
        '"obsidian_local": {',
        '"mode": "local"',
    )
    for snippet in required_caps:
        if snippet not in text:
            errors.append(f"gateway capabilities missing snippet: {snippet}")
    return errors


def _check_disabled_reason_snippets(
    gateway_text: str | None = None,
    http_text: str | None = None,
    http_utils_text: str | None = None,
) -> list[str]:
    errors: list[str] = []
    gateway_text = (
        gateway_text
        if gateway_text is not None
        else GATEWAY_MAIN.read_text(encoding="utf-8")
    )
    http_text = (
        http_text if http_text is not None else HTTP_TRANSPORT.read_text(encoding="utf-8")
    )
    http_utils_text = (
        http_utils_text
        if http_utils_text is not None
        else HTTP_TRANSPORT_UTILS.read_text(encoding="utf-8")
    )

    contract = json.loads(DISABLED_REASON_CONTRACT.read_text(encoding="utf-8"))
    gateway_snippets = contract.get("gateway_snippets", [])
    http_snippets = contract.get("http_snippets", [])
    if not isinstance(gateway_snippets, list) or not gateway_snippets:
        return ["obsidian_disabled_reason_contract gateway_snippets must be non-empty list"]
    if not isinstance(http_snippets, list) or not http_snippets:
        return ["obsidian_disabled_reason_contract http_snippets must be non-empty list"]
    if any(not isinstance(snippet, str) or not snippet for snippet in gateway_snippets):
        return ["obsidian_disabled_reason_contract gateway_snippets must contain non-empty strings"]
    if any(not isinstance(snippet, str) or not snippet for snippet in http_snippets):
        return ["obsidian_disabled_reason_contract http_snippets must contain non-empty strings"]

    for snippet in gateway_snippets:
        if snippet not in gateway_text:
            errors.append(f"gateway disabled reason missing snippet: {snippet}")

    missing_http_snippets = [snippet for snippet in http_snippets if snippet not in http_text]
    if missing_http_snippets:
        try:
            tree = ast.parse(http_text)
        except SyntaxError:
            tree = None
        helper_fn = _find_function(tree, "_http_obsidian_disabled_reason") if tree else None
        helper_delegates = bool(
            helper_fn is not None
            and _sync_function_calls_name(helper_fn, "http_obsidian_disabled_reason")
        )
        if helper_delegates:
            for snippet in http_snippets:
                if snippet not in http_utils_text:
                    errors.append(f"HTTP disabled reason missing snippet: {snippet}")
        else:
            for snippet in missing_http_snippets:
                errors.append(f"HTTP disabled reason missing snippet: {snippet}")
    return errors


def _check_http_transport_contract() -> list[str]:
    errors: list[str] = []
    text = HTTP_TRANSPORT.read_text(encoding="utf-8")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    http_tools = payload.get("http_obsidian_tools", [])

    if "if ENABLE_HTTP_OBSIDIAN_TOOLS:" not in text:
        errors.append("HTTP transport must gate Obsidian tools with ENABLE_HTTP_OBSIDIAN_TOOLS")
    elif not _http_obsidian_tools_defined_under_flag(text, http_tools):
        errors.append(
            "HTTP transport must define all http_obsidian_tools under ENABLE_HTTP_OBSIDIAN_TOOLS gate"
        )
    required_caps = (
        '"obsidian": {',
        '"obsidian_http": {',
        '"mode": "http"',
    )
    for snippet in required_caps:
        if snippet not in text:
            errors.append(f"HTTP capabilities missing snippet: {snippet}")
    return errors


def _dict_value_for_key(node: ast.Dict, key_name: str) -> ast.AST | None:
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and key.value == key_name:
            return value
    return None


def _is_name(value: ast.AST | None, expected: str) -> bool:
    return isinstance(value, ast.Name) and value.id == expected


def _check_obsidian_capabilities_payload_semantics(
    text: str,
    *,
    label: str,
    expected_mode: str,
    expected_secondary_key: str,
) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(text)
    fn = _find_async_function(tree, "brain_capabilities")
    if fn is None:
        return [f"{label} missing brain_capabilities"]

    return_dict: ast.Dict | None = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
            return_dict = node.value
            break
    if return_dict is None:
        return [f"{label} brain_capabilities must return a dict payload"]

    obsidian_value = _dict_value_for_key(return_dict, "obsidian")
    secondary_value = _dict_value_for_key(return_dict, expected_secondary_key)
    if not isinstance(obsidian_value, ast.Dict):
        errors.append(f"{label} brain_capabilities must include obsidian object")
        return errors
    if not isinstance(secondary_value, ast.Dict):
        errors.append(
            f"{label} brain_capabilities must include {expected_secondary_key} object"
        )
        return errors

    mode_value = _dict_value_for_key(obsidian_value, "mode")
    if not (isinstance(mode_value, ast.Constant) and mode_value.value == expected_mode):
        errors.append(
            f"{label} obsidian.mode must be constant '{expected_mode}'"
        )

    for key_name, expected_var in (
        ("status", "obsidian_status"),
        ("tools", "obsidian_tools"),
        ("reason", "obsidian_reason"),
    ):
        if not _is_name(_dict_value_for_key(obsidian_value, key_name), expected_var):
            errors.append(
                f"{label} obsidian.{key_name} must reference {expected_var}"
            )
        if not _is_name(_dict_value_for_key(secondary_value, key_name), expected_var):
            errors.append(
                f"{label} {expected_secondary_key}.{key_name} must reference {expected_var}"
            )

    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_manifest())
    errors.extend(_check_gateway_gating())
    errors.extend(_check_disabled_reason_snippets())
    errors.extend(_check_http_transport_contract())
    errors.extend(
        _check_obsidian_capabilities_payload_semantics(
            GATEWAY_MAIN.read_text(encoding="utf-8"),
            label="gateway",
            expected_mode="local",
            expected_secondary_key="obsidian_local",
        )
    )
    errors.extend(
        _check_obsidian_capabilities_payload_semantics(
            HTTP_TRANSPORT.read_text(encoding="utf-8"),
            label="HTTP transport",
            expected_mode="http",
            expected_secondary_key="obsidian_http",
        )
    )
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Obsidian contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
