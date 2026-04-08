#!/usr/bin/env python3
"""Guardrail: enforce Obsidian tool gating and capabilities contract invariants."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "unified/contracts/capabilities_manifest.json"
GATEWAY_MAIN = ROOT / "unified/mcp-gateway/src/main.py"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"


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


def _extract_function_block(text: str, function_name: str) -> str:
    pattern = rf"^async def {function_name}\(.*?(?=^async def |\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if not match:
        raise RuntimeError(f"missing function: {function_name}")
    return match.group(0)


def _check_gateway_gating() -> list[str]:
    errors: list[str] = []
    text = GATEWAY_MAIN.read_text(encoding="utf-8")
    if 'OBSIDIAN_LOCAL_TOOLS_ENV = "ENABLE_LOCAL_OBSIDIAN_TOOLS"' not in text:
        errors.append("gateway must define ENABLE_LOCAL_OBSIDIAN_TOOLS env constant")
    if "_require_obsidian_local_tools_enabled()" not in text:
        errors.append("gateway must guard local obsidian tools with _require_obsidian_local_tools_enabled")

    guarded_tools = (
        "brain_obsidian_vaults",
        "brain_obsidian_read_note",
        "brain_obsidian_sync",
        "brain_obsidian_write_note",
        "brain_obsidian_export",
        "brain_obsidian_collection",
        "brain_obsidian_bidirectional_sync",
        "brain_obsidian_sync_status",
        "brain_obsidian_update_note",
    )
    for tool in guarded_tools:
        try:
            block = _extract_function_block(text, tool)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        if "_require_obsidian_local_tools_enabled()" not in block:
            errors.append(f"{tool} must call _require_obsidian_local_tools_enabled()")

    required_caps = (
        '"obsidian": {',
        '"obsidian_local": {',
        '"mode": "local"',
    )
    for snippet in required_caps:
        if snippet not in text:
            errors.append(f"gateway capabilities missing snippet: {snippet}")
    return errors


def _check_http_transport_contract() -> list[str]:
    errors: list[str] = []
    text = HTTP_TRANSPORT.read_text(encoding="utf-8")
    if "if ENABLE_HTTP_OBSIDIAN_TOOLS:" not in text:
        errors.append("HTTP transport must gate Obsidian tools with ENABLE_HTTP_OBSIDIAN_TOOLS")
    required_caps = (
        '"obsidian": {',
        '"obsidian_http": {',
        '"mode": "http"',
    )
    for snippet in required_caps:
        if snippet not in text:
            errors.append(f"HTTP capabilities missing snippet: {snippet}")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_manifest())
    errors.extend(_check_gateway_gating())
    errors.extend(_check_http_transport_contract())
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Obsidian contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
