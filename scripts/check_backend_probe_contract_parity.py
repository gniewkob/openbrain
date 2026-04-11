#!/usr/bin/env python3
"""Guardrail: enforce backend health probe contract parity across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
CONTRACT = ROOT / "unified/contracts/backend_probe_guardrail_contract.json"


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("backend_probe_guardrail_contract must be object")
    for key in ("readyz_paths", "fallback_paths", "probe_labels", "reason_fragments"):
        value = payload.get(key)
        if not isinstance(value, list) or not value:
            raise ValueError(f"contract {key} must be non-empty list")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"contract {key} must contain non-empty strings")
    return payload


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _find_fn(tree: ast.Module, fn_name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            return node
    raise ValueError(f"{fn_name} not found")


def _extract_readyz_paths(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> tuple[str, ...]:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "readyz_paths" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Tuple):
            continue
        values: list[str] = []
        for elt in node.value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value)
        return tuple(values)
    raise ValueError("readyz_paths tuple not found")


def _extract_health_request_paths(
    fn: ast.AsyncFunctionDef | ast.FunctionDef, fallback_paths: set[str]
) -> set[str]:
    paths: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if value in fallback_paths:
            paths.add(value)
    return paths


def _extract_probe_labels(
    fn: ast.AsyncFunctionDef | ast.FunctionDef, required_probe_labels: set[str]
) -> set[str]:
    labels: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in required_probe_labels:
                labels.add(node.value)
    return labels


def _has_reason_fragment(fn: ast.AsyncFunctionDef | ast.FunctionDef, fragment: str) -> bool:
    return any(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and fragment in node.value
        for node in ast.walk(fn)
    )


def _extract_contract(
    source: str, fallback_paths: set[str], required_probe_labels: set[str]
) -> dict[str, object]:
    tree = ast.parse(source)
    fn = _find_fn(tree, "_get_backend_status")
    return {
        "readyz_paths": _extract_readyz_paths(fn),
        "fallback_paths": _extract_health_request_paths(fn, fallback_paths),
        "probe_labels": _extract_probe_labels(fn, required_probe_labels),
        "has_readyz_reason_fragment": _has_reason_fragment(fn, "/readyz probe failed"),
        "has_healthz_reason_fragment": _has_reason_fragment(fn, "/healthz probe failed"),
        "has_api_health_reason_fragment": _has_reason_fragment(fn, "/api/v1/health probe failed"),
    }


def _check_backend_probe_contract_parity(transport_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    contract = _load_contract()
    required_readyz_paths = tuple(str(item) for item in contract["readyz_paths"])
    required_fallback_paths = {str(item) for item in contract["fallback_paths"]}
    required_probe_labels = {str(item) for item in contract["probe_labels"]}
    reason_fragments = [str(item) for item in contract["reason_fragments"]]
    if len(reason_fragments) != 3:
        errors.append("contract reason_fragments must contain exactly 3 entries")
        return errors

    transport = _extract_contract(
        transport_src, required_fallback_paths, required_probe_labels
    )
    gateway = _extract_contract(gateway_src, required_fallback_paths, required_probe_labels)

    for label, contract in (("transport", transport), ("gateway", gateway)):
        if contract["readyz_paths"] != required_readyz_paths:
            errors.append(
                f"{label} readyz_paths drift: expected={required_readyz_paths} got={contract['readyz_paths']}"
            )
        missing_paths = required_fallback_paths - set(contract["fallback_paths"])  # type: ignore[arg-type]
        if missing_paths:
            errors.append(f"{label} missing fallback probe paths: {sorted(missing_paths)}")
        missing_labels = required_probe_labels - set(contract["probe_labels"])  # type: ignore[arg-type]
        if missing_labels:
            errors.append(f"{label} missing probe labels: {sorted(missing_labels)}")
        reason_flags = (
            ("has_readyz_reason_fragment", reason_fragments[0]),
            ("has_healthz_reason_fragment", reason_fragments[1]),
            ("has_api_health_reason_fragment", reason_fragments[2]),
        )
        for flag_name, fragment in reason_flags:
            if not contract[flag_name]:
                errors.append(f"{label} missing '{fragment}' reason fragment")

    if transport != gateway:
        errors.append(f"backend probe contract drift: transport={transport} gateway={gateway}")
    return errors


def main() -> int:
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_backend_probe_contract_parity(transport_src, gateway_src)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Backend probe contract parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
