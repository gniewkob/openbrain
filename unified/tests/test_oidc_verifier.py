"""Tests for OIDCVerifier.verify_token — covers lines 154-170 and 173-177.

Lines 154-170: JWT decode success path → returns claims
Lines 173-177: non-ValueError exception in JWT flow → wrapped ValueError
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_oidc_verifier():
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier(
        issuer_url="https://auth.example.com",
        audience="my-app",
    )
    return verifier


# ---------------------------------------------------------------------------
# Lines 154-170 — JWT decode success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_token_returns_claims_on_valid_jwt():
    """jwt.decode succeeds with valid sub → returns claims (lines 154-170)."""
    verifier = _make_oidc_verifier()

    mock_metadata = MagicMock()
    mock_metadata.issuer = "https://auth.example.com"
    mock_metadata.jwks_uri = "https://auth.example.com/.well-known/jwks.json"

    # Inject pre-set metadata so _get_metadata() doesn't make HTTP calls
    verifier._metadata = mock_metadata
    verifier._metadata_fetched_at = 1e12  # far future — always fresh

    mock_signing_key = MagicMock()
    mock_signing_key.key = "test-key"

    mock_jwk_client = MagicMock()
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
    verifier._jwk_client = mock_jwk_client

    valid_claims = {"sub": "user123", "exp": 9999999999, "iat": 1000000000}

    # Use a fake 3-part JWT so the format check passes
    fake_token = "header.payload.signature"

    with (
        patch("src.auth.asyncio.to_thread", AsyncMock(return_value=mock_signing_key)),
        patch("src.auth.jwt.decode", return_value=valid_claims),
    ):
        result = await verifier.verify_token(fake_token)

    assert result == valid_claims
    assert result["sub"] == "user123"


# ---------------------------------------------------------------------------
# Lines 173-177 — non-ValueError exception → wrapped ValueError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_token_raises_when_sub_missing():
    """jwt.decode returns claims with empty sub → ValueError (line 169)."""
    verifier = _make_oidc_verifier()

    mock_metadata = MagicMock()
    mock_metadata.issuer = "https://auth.example.com"
    verifier._metadata = mock_metadata
    verifier._metadata_fetched_at = 1e12

    mock_signing_key = MagicMock()
    mock_signing_key.key = "test-key"
    verifier._jwk_client = MagicMock()
    verifier._jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key

    fake_token = "header.payload.signature"
    # Claims with empty sub
    empty_sub_claims = {"sub": "   ", "exp": 9999999999, "iat": 1000000000}

    with (
        patch("src.auth.asyncio.to_thread", AsyncMock(return_value=mock_signing_key)),
        patch("src.auth.jwt.decode", return_value=empty_sub_claims),
    ):
        with pytest.raises(ValueError, match="missing required 'sub'"):
            await verifier.verify_token(fake_token)


@pytest.mark.asyncio
async def test_verify_token_wraps_unexpected_exception():
    """jwt.decode raises non-ValueError → caught, wrapped in ValueError (lines 173-177)."""
    verifier = _make_oidc_verifier()

    mock_metadata = MagicMock()
    mock_metadata.issuer = "https://auth.example.com"
    mock_metadata.jwks_uri = "https://auth.example.com/.well-known/jwks.json"

    verifier._metadata = mock_metadata
    verifier._metadata_fetched_at = 1e12

    mock_signing_key = MagicMock()
    mock_signing_key.key = "test-key"

    mock_jwk_client = MagicMock()
    mock_jwk_client.get_signing_key_from_jwt.return_value = mock_signing_key
    verifier._jwk_client = mock_jwk_client

    fake_token = "header.payload.signature"

    # jwt.decode raises a non-ValueError (e.g. RuntimeError)
    with (
        patch("src.auth.asyncio.to_thread", AsyncMock(return_value=mock_signing_key)),
        patch("src.auth.jwt.decode", side_effect=RuntimeError("unexpected JWT error")),
    ):
        with pytest.raises(ValueError, match="Invalid access token"):
            await verifier.verify_token(fake_token)
