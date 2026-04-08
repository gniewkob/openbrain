#!/usr/bin/env python3
"""Guardrail: ensure capabilities status semantics stay truthful across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/capabilities_response_contract.json"
METADATA = ROOT / "unified/contracts/capabilities_metadata.json"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
STDIO_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _check_contract() -> list[str]:
    errors: list[str] = []
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required_top_level = set(payload.get("required_top_level_keys", []))
    if "health" not in required_top_level:
        errors.append("contract required_top_level_keys must include 'health'")

    required_health = set(payload.get("health_required_keys", []))
    expected_health = {"overall", "source", "components"}
    if required_health != expected_health:
        errors.append(
            "contract health_required_keys must be exactly "
            f"{sorted(expected_health)} (got {sorted(required_health)})"
        )

    required_components = set(payload.get("health_component_required_keys", []))
    expected_components = {"api", "db", "vector_store", "obsidian"}
    if required_components != expected_components:
        errors.append(
            "contract health_component_required_keys must be exactly "
            f"{sorted(expected_components)} (got {sorted(required_components)})"
        )

    overall_values = set(payload.get("health_overall_values", []))
    expected_overall_values = {"healthy", "degraded", "unavailable"}
    if overall_values != expected_overall_values:
        errors.append(
            "contract health_overall_values must be exactly "
            f"{sorted(expected_overall_values)} (got {sorted(overall_values)})"
        )
    return errors


def _check_metadata() -> list[str]:
    errors: list[str] = []
    payload = json.loads(METADATA.read_text(encoding="utf-8"))
    changelog = payload.get("schema_changelog", {})
    if payload.get("api_version") != "2.3.0":
        errors.append("capabilities metadata api_version must be 2.3.0")
    change_230 = str(changelog.get("2.3.0", ""))
    if "health" not in change_230:
        errors.append("schema_changelog[2.3.0] must describe health semantics change")
    return errors


def _find_async_function(tree: ast.AST, name: str) -> ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    return None


def _has_health_payload_in_brain_capabilities(text: str) -> bool:
    tree = ast.parse(text)
    fn = _find_async_function(tree, "brain_capabilities")
    if fn is None:
        return False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        for key, item in zip(value.keys, value.values):
            if not isinstance(key, ast.Constant) or key.value != "health":
                continue
            if isinstance(item, ast.Name) and item.id == "health":
                return True
    return False


def _check_health_probe_fallback_semantics(text: str, label: str) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(text)
    fn = _find_async_function(tree, "_get_backend_status")
    if fn is None:
        return [f"{label} must define _get_backend_status"]
    constants = {
        node.value for node in ast.walk(fn) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    if "/api/v1/health" not in constants:
        errors.append(f"{label} must probe /api/v1/health before reporting unavailable")
    if "api_health_fallback" not in constants:
        errors.append(f"{label} must include api_health_fallback probe marker")
    return errors


def _check_transport_source(path: Path, label: str) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if not _has_health_payload_in_brain_capabilities(text):
        errors.append(f"{label} must include health payload in capabilities response")
    errors.extend(_check_health_probe_fallback_semantics(text, label))
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_contract())
    errors.extend(_check_metadata())
    errors.extend(_check_transport_source(HTTP_TRANSPORT, "HTTP transport"))
    errors.extend(_check_transport_source(STDIO_GATEWAY, "stdio gateway"))
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Capabilities truthfulness guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
