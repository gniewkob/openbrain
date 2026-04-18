from __future__ import annotations

import os

from src.http_error_adapter import (
    backend_error_message,
    backend_request_failure_message,
)


def test_backend_error_message_dev_includes_detail() -> None:
    os.environ.pop("ENV", None)
    msg = backend_error_message(500, {"detail": "sensitive"})
    assert "500" in msg
    assert "sensitive" in msg


def test_backend_error_message_prod_masks_detail() -> None:
    os.environ["ENV"] = "production"
    msg = backend_error_message(500, {"detail": "sensitive"})
    assert "500" in msg
    assert "Internal server error" in msg
    assert "sensitive" not in msg
    os.environ.pop("ENV", None)


def test_backend_request_failure_message_dev_includes_error() -> None:
    os.environ.pop("ENV", None)
    msg = backend_request_failure_message(RuntimeError("connect timeout"))
    assert "Backend request failed" in msg
    assert "connect timeout" in msg


def test_backend_request_failure_message_prod_masks_error() -> None:
    os.environ["ENV"] = "production"
    msg = backend_request_failure_message(RuntimeError("connect timeout"))
    assert msg == "Backend request failed: upstream unavailable"
    assert "connect timeout" not in msg
    os.environ.pop("ENV", None)
