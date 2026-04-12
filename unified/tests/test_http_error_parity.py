from __future__ import annotations

import os
import sys
from pathlib import Path

from src.http_error_adapter import (
    backend_error_message as transport_backend_error_message,
)
from src.http_error_adapter import (
    backend_request_failure_message as transport_request_failure_message,
)

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_TESTS = ROOT / "mcp-gateway" / "tests"
if str(GATEWAY_TESTS) not in sys.path:
    sys.path.insert(0, str(GATEWAY_TESTS))

from helpers import load_gateway_module  # noqa: E402

gateway_http_error = load_gateway_module("http_error_adapter")


def test_backend_error_message_parity_in_production() -> None:
    os.environ["ENV"] = "production"
    try:
        detail = {"detail": "sensitive internal info"}
        for status in (401, 403, 404, 422, 500):
            transport_msg = transport_backend_error_message(status, detail)
            gateway_msg = gateway_http_error.backend_error_message(status, detail)
            assert transport_msg == gateway_msg
    finally:
        os.environ.pop("ENV", None)


def test_backend_error_message_parity_in_development() -> None:
    os.environ.pop("ENV", None)
    detail = {"detail": "debug detail"}
    transport_msg = transport_backend_error_message(500, detail)
    gateway_msg = gateway_http_error.backend_error_message(500, detail)
    assert transport_msg == gateway_msg


def test_request_failure_message_parity_in_production() -> None:
    os.environ["ENV"] = "production"
    try:
        err = RuntimeError("connect timeout")
        transport_msg = transport_request_failure_message(err)
        gateway_msg = gateway_http_error.backend_request_failure_message(err)
        assert transport_msg == gateway_msg
    finally:
        os.environ.pop("ENV", None)


def test_request_failure_message_parity_in_development() -> None:
    os.environ.pop("ENV", None)
    err = RuntimeError("connect timeout")
    transport_msg = transport_request_failure_message(err)
    gateway_msg = gateway_http_error.backend_request_failure_message(err)
    assert transport_msg == gateway_msg


def test_missing_session_id_hint_parity_and_shape() -> None:
    os.environ.pop("ENV", None)
    detail = {"detail": "Missing session ID"}
    transport_msg = transport_backend_error_message(400, detail)
    gateway_msg = gateway_http_error.backend_error_message(400, detail)
    assert transport_msg == gateway_msg
    assert transport_msg == (
        "Backend 400: Missing MCP session context; reconnect the MCP HTTP client and retry."
    )
