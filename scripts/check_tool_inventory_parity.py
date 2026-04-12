#!/usr/bin/env python3
"""Guardrail: keep MCP tool inventory aligned with canonical transport posture."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
MANIFEST = ROOT / "unified/contracts/capabilities_manifest.json"
CONTRACT = ROOT / "unified/contracts/tool_inventory_guardrail_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_mcp_tools(source: str) -> set[str]:
    tree = ast.parse(source)
    tools: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "mcp"
                and decorator.func.attr == "tool"
            ):
                tools.add(node.name)
                break
    return tools


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("tool_inventory_guardrail_contract must be a JSON object")

    manifest_key = payload.get("manifest_obsidian_tools_key")
    if not isinstance(manifest_key, str) or not manifest_key:
        raise ValueError("contract manifest_obsidian_tools_key must be non-empty string")

    tool_name_prefix = payload.get("tool_name_prefix")
    if not isinstance(tool_name_prefix, str) or not tool_name_prefix:
        raise ValueError("contract tool_name_prefix must be non-empty string")

    obsidian_prefix = payload.get("obsidian_tool_prefix")
    if not isinstance(obsidian_prefix, str) or not obsidian_prefix:
        raise ValueError("contract obsidian_tool_prefix must be non-empty string")

    require_gateway_obsidian = payload.get("require_gateway_obsidian_tools")
    if not isinstance(require_gateway_obsidian, bool):
        raise ValueError("contract require_gateway_obsidian_tools must be bool")

    return payload


def _load_expected_http_obsidian_tools(contract: dict[str, object]) -> tuple[set[str], list[str]]:
    errors: list[str] = []
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_key = str(contract["manifest_obsidian_tools_key"])
    tool_prefix = str(contract["tool_name_prefix"])
    tools = raw.get(manifest_key)
    if not isinstance(tools, list) or not tools:
        return set(), [f"capabilities_manifest {manifest_key} must be non-empty list"]
    if any(not isinstance(tool, str) or not tool for tool in tools):
        return (
            set(),
            [f"capabilities_manifest {manifest_key} must contain non-empty strings"],
        )
    return {f"{tool_prefix}{tool}" for tool in tools}, errors


def _check_tool_inventory_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    contract = _load_contract()
    obsidian_prefix = str(contract["obsidian_tool_prefix"])
    expected_http_obsidian, manifest_errors = _load_expected_http_obsidian_tools(contract)
    errors.extend(manifest_errors)
    if manifest_errors:
        return errors

    http_tools = _extract_mcp_tools(http_src)
    gateway_tools = _extract_mcp_tools(gateway_src)

    http_obsidian = {name for name in http_tools if name.startswith(obsidian_prefix)}
    gateway_obsidian = {name for name in gateway_tools if name.startswith(obsidian_prefix)}
    if bool(contract["require_gateway_obsidian_tools"]) and not gateway_obsidian:
        errors.append("gateway must expose obsidian MCP tools")
    if http_obsidian != expected_http_obsidian:
        errors.append(
            "HTTP transport obsidian tool set drifted: "
            f"expected={sorted(expected_http_obsidian)} actual={sorted(http_obsidian)}"
        )
    if not http_obsidian.issubset(gateway_obsidian):
        errors.append(
            "HTTP transport exposes obsidian tool not present in gateway: "
            f"{sorted(http_obsidian - gateway_obsidian)}"
        )

    http_non_obsidian = http_tools - http_obsidian
    gateway_non_obsidian = gateway_tools - gateway_obsidian
    if http_non_obsidian != gateway_non_obsidian:
        errors.append(
            "non-obsidian tool inventory drift: "
            f"http_only={sorted(http_non_obsidian - gateway_non_obsidian)} "
            f"gateway_only={sorted(gateway_non_obsidian - http_non_obsidian)}"
        )

    return errors


def main() -> int:
    http_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_tool_inventory_parity(http_src, gateway_src)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Tool inventory parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
