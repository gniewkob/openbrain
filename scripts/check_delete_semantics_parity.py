#!/usr/bin/env python3
"""Guardrail: keep brain_delete semantics aligned across MCP transports."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"

NOT_FOUND_MESSAGE = "Memory not found: {memory_id}"
FORBIDDEN_MESSAGE = "Cannot delete corporate memories. Use deprecation instead."


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _check_gateway_delete_semantics(source: str) -> list[str]:
    errors: list[str] = []
    if not re.search(r"allow_statuses\s*=\s*\{\s*403\s*,\s*404\s*\}", source):
        errors.append("gateway brain_delete must allow 403 and 404 passthrough")
    if "backend_error_message(" not in source:
        errors.append("gateway delete path must rely on backend_error_message mapping")
    if NOT_FOUND_MESSAGE not in source:
        errors.append("gateway brain_delete must expose canonical not-found message")
    if FORBIDDEN_MESSAGE not in source:
        errors.append("gateway brain_delete must expose canonical forbidden message")
    return errors


def _check_transport_delete_semantics(source: str) -> list[str]:
    errors: list[str] = []
    if not re.search(r"response\.status_code\s*==\s*404", source):
        errors.append("transport brain_delete must map 404 explicitly")
    if not re.search(r"response\.status_code\s*==\s*403", source):
        errors.append("transport brain_delete must map 403 explicitly")
    if "backend_error_message(" not in source:
        errors.append("transport delete path must rely on backend_error_message mapping")
    if NOT_FOUND_MESSAGE not in source:
        errors.append("transport brain_delete must expose canonical not-found message")
    if FORBIDDEN_MESSAGE not in source:
        errors.append("transport brain_delete must expose canonical forbidden message")
    return errors


def main() -> int:
    gateway_source = MCP_GATEWAY.read_text(encoding="utf-8")
    transport_source = MCP_TRANSPORT.read_text(encoding="utf-8")

    errors: list[str] = []
    errors.extend(_check_gateway_delete_semantics(gateway_source))
    errors.extend(_check_transport_delete_semantics(transport_source))

    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Delete semantics parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
