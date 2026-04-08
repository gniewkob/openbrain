from __future__ import annotations

import os

from src.http_error_adapter import backend_error_message


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
