#!/usr/bin/env python3
"""Guardrail: enforce backend health probe contract parity across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"

REQUIRED_READYZ_PATHS = ("/readyz", "/api/v1/readyz")
REQUIRED_FALLBACK_PATHS = {"/healthz", "/api/v1/health"}
REQUIRED_PROBE_LABELS = {"readyz", "healthz_fallback", "api_health_fallback"}


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


def _extract_health_request_paths(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    paths: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if value in REQUIRED_FALLBACK_PATHS:
            paths.add(value)
    return paths


def _extract_probe_labels(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> set[str]:
    labels: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in REQUIRED_PROBE_LABELS:
                labels.add(node.value)
    return labels


def _has_reason_fragment(fn: ast.AsyncFunctionDef | ast.FunctionDef, fragment: str) -> bool:
    return any(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and fragment in node.value
        for node in ast.walk(fn)
    )


def _extract_contract(source: str) -> dict[str, object]:
    tree = ast.parse(source)
    fn = _find_fn(tree, "_get_backend_status")
    return {
        "readyz_paths": _extract_readyz_paths(fn),
        "fallback_paths": _extract_health_request_paths(fn),
        "probe_labels": _extract_probe_labels(fn),
        "has_readyz_reason_fragment": _has_reason_fragment(fn, "/readyz probe failed"),
        "has_healthz_reason_fragment": _has_reason_fragment(fn, "/healthz probe failed"),
        "has_api_health_reason_fragment": _has_reason_fragment(fn, "/api/v1/health probe failed"),
    }


def _check_backend_probe_contract_parity(transport_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    transport = _extract_contract(transport_src)
    gateway = _extract_contract(gateway_src)

    for label, contract in (("transport", transport), ("gateway", gateway)):
        if contract["readyz_paths"] != REQUIRED_READYZ_PATHS:
            errors.append(
                f"{label} readyz_paths drift: expected={REQUIRED_READYZ_PATHS} got={contract['readyz_paths']}"
            )
        missing_paths = REQUIRED_FALLBACK_PATHS - set(contract["fallback_paths"])  # type: ignore[arg-type]
        if missing_paths:
            errors.append(f"{label} missing fallback probe paths: {sorted(missing_paths)}")
        missing_labels = REQUIRED_PROBE_LABELS - set(contract["probe_labels"])  # type: ignore[arg-type]
        if missing_labels:
            errors.append(f"{label} missing probe labels: {sorted(missing_labels)}")
        if not contract["has_readyz_reason_fragment"]:
            errors.append(f"{label} missing '/readyz probe failed' reason fragment")
        if not contract["has_healthz_reason_fragment"]:
            errors.append(f"{label} missing '/healthz probe failed' reason fragment")
        if not contract["has_api_health_reason_fragment"]:
            errors.append(f"{label} missing '/api/v1/health probe failed' reason fragment")

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
