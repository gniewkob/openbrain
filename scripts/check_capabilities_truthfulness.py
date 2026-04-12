#!/usr/bin/env python3
"""Guardrail: ensure capabilities status semantics stay truthful across transports."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/capabilities_response_contract.json"
METADATA = ROOT / "unified/contracts/capabilities_metadata.json"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
STDIO_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
HTTP_CAPABILITIES_HEALTH = ROOT / "unified/src/capabilities_health.py"
GATEWAY_CAPABILITIES_HEALTH = ROOT / "unified/mcp-gateway/src/capabilities_health.py"


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

    required_tier_keys = set(payload.get("tier_required_keys", []))
    expected_tier_keys = {"status", "tools"}
    if required_tier_keys != expected_tier_keys:
        errors.append(
            "contract tier_required_keys must be exactly "
            f"{sorted(expected_tier_keys)} (got {sorted(required_tier_keys)})"
        )

    tier_status_values = set(payload.get("tier_status_values", []))
    expected_tier_status_values = {"stable", "active", "guarded"}
    if tier_status_values != expected_tier_status_values:
        errors.append(
            "contract tier_status_values must be exactly "
            f"{sorted(expected_tier_status_values)} (got {sorted(tier_status_values)})"
        )
    return errors


def _check_metadata() -> list[str]:
    errors: list[str] = []
    payload = json.loads(METADATA.read_text(encoding="utf-8"))
    api_version = payload.get("api_version")
    changelog = payload.get("schema_changelog", {})
    if not isinstance(api_version, str) or not re.fullmatch(r"^\d+\.\d+\.\d+$", api_version):
        errors.append("capabilities metadata api_version must match MAJOR.MINOR.PATCH")
        return errors
    if not isinstance(changelog, dict):
        errors.append("capabilities metadata schema_changelog must be an object")
        return errors
    if api_version not in changelog:
        errors.append("capabilities metadata schema_changelog must include api_version entry")

    health_entries = [
        str(message).lower() for message in changelog.values() if isinstance(message, str)
    ]
    if not any("health" in message for message in health_entries):
        errors.append(
            "capabilities metadata schema_changelog must contain at least one health semantics entry"
        )
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
    if "/readyz" not in constants:
        errors.append(f"{label} must probe /readyz as primary readiness endpoint")
    if "/api/v1/readyz" not in constants:
        errors.append(
            f"{label} must probe /api/v1/readyz as readiness compatibility fallback"
        )
    if "readyz" not in constants:
        errors.append(f"{label} must include readyz probe marker")
    if "/healthz" not in constants:
        errors.append(f"{label} must probe /healthz as fallback endpoint")
    if "healthz_fallback" not in constants:
        errors.append(f"{label} must include healthz_fallback probe marker")
    if "/api/v1/health" not in constants:
        errors.append(f"{label} must probe /api/v1/health before reporting unavailable")
    if "api_health_fallback" not in constants:
        errors.append(f"{label} must include api_health_fallback probe marker")
    if "readyz_status_code" not in constants:
        errors.append(f"{label} must include readyz_status_code in backend probe payload")
    return errors


def _check_transport_source(path: Path, label: str) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    if not _has_health_payload_in_brain_capabilities(text):
        errors.append(f"{label} must include health payload in capabilities response")
    errors.extend(_check_health_probe_fallback_semantics(text, label))
    return errors


def _check_capabilities_health_contract(path: Path, label: str) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    fn = _find_async_function(tree, "build_capabilities_health")
    if fn is None:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "build_capabilities_health":
                fn = node
                break
    if fn is None:
        return [f"{label} must define build_capabilities_health"]

    has_source_probe_mapping = False
    has_obsidian_enabled_disabled_mapping = False

    for node in ast.walk(fn):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant):
                continue
            if key.value == "source" and isinstance(value, ast.Call):
                if (
                    isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "backend"
                    and value.func.attr == "get"
                    and len(value.args) >= 1
                    and isinstance(value.args[0], ast.Constant)
                    and value.args[0].value == "probe"
                ):
                    has_source_probe_mapping = True
            if key.value == "obsidian" and isinstance(value, ast.IfExp):
                if (
                    isinstance(value.body, ast.Constant)
                    and value.body.value == "enabled"
                    and isinstance(value.orelse, ast.Constant)
                    and value.orelse.value == "disabled"
                ):
                    has_obsidian_enabled_disabled_mapping = True

    if not has_source_probe_mapping:
        errors.append(
            f"{label} build_capabilities_health must set health.source from backend.get('probe', ...)"
        )
    if not has_obsidian_enabled_disabled_mapping:
        errors.append(
            f"{label} build_capabilities_health must map obsidian component to enabled/disabled"
        )
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_contract())
    errors.extend(_check_metadata())
    errors.extend(_check_transport_source(HTTP_TRANSPORT, "HTTP transport"))
    errors.extend(_check_transport_source(STDIO_GATEWAY, "stdio gateway"))
    errors.extend(
        _check_capabilities_health_contract(
            HTTP_CAPABILITIES_HEALTH, "HTTP capabilities health"
        )
    )
    errors.extend(
        _check_capabilities_health_contract(
            GATEWAY_CAPABILITIES_HEALTH, "Gateway capabilities health"
        )
    )
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Capabilities truthfulness guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
