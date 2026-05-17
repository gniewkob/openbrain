"""Unit tests for the centralized configuration module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.config import is_public_mode


def test_is_public_mode_true():
    """Test that is_public_mode returns True when public_mode is True in config."""
    mock_config = MagicMock()
    mock_config.auth.public_mode = True

    with patch("src.config.get_config", return_value=mock_config):
        assert is_public_mode() is True


def test_is_public_mode_false():
    """Test that is_public_mode returns False when public_mode is False in config."""
    mock_config = MagicMock()
    mock_config.auth.public_mode = False

    with patch("src.config.get_config", return_value=mock_config):
        assert is_public_mode() is False
