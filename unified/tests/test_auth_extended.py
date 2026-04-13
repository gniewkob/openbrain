"""Extended auth.py tests — policy registry, claims helpers, OIDC, require_auth."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# _load_policy_registry_from_json  (lines 210-219)
# ---------------------------------------------------------------------------


def test_load_policy_registry_from_json_empty_env():
    from src.auth import _load_policy_registry_from_json

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OPENBRAIN_POLICY_REGISTRY_JSON", None)
        with patch("src.auth.POLICY_REGISTRY_JSON", ""):
            result = _load_policy_registry_from_json()
    assert result == {"tenants": {}, "subjects": {}}


def test_load_policy_registry_from_json_valid():
    from src.auth import _load_policy_registry_from_json

    data = json.dumps({"tenants": {"t1": {}}, "subjects": {}})
    with patch("src.auth.POLICY_REGISTRY_JSON", data):
        result = _load_policy_registry_from_json()
    assert "t1" in result["tenants"]


def test_load_policy_registry_from_json_invalid_json():
    from src.auth import _load_policy_registry_from_json

    with patch("src.auth.POLICY_REGISTRY_JSON", "not-json"):
        with pytest.raises(RuntimeError, match="not valid JSON"):
            _load_policy_registry_from_json()


def test_load_policy_registry_from_json_non_dict():
    from src.auth import _load_policy_registry_from_json

    with patch("src.auth.POLICY_REGISTRY_JSON", "[1, 2, 3]"):
        with pytest.raises(RuntimeError, match="must be a JSON object"):
            _load_policy_registry_from_json()


# ---------------------------------------------------------------------------
# _load_policy_registry_from_file  (lines 222-236)
# ---------------------------------------------------------------------------


def test_load_policy_registry_from_file_no_path():
    from src.auth import _load_policy_registry_from_file

    with patch("src.auth.POLICY_REGISTRY_PATH", ""):
        result = _load_policy_registry_from_file()
    assert result == {"tenants": {}, "subjects": {}}


def test_load_policy_registry_from_file_missing_file():
    from src.auth import _load_policy_registry_from_file

    with patch("src.auth.POLICY_REGISTRY_PATH", "/nonexistent/path/policy.json"):
        result = _load_policy_registry_from_file()
    assert result == {"tenants": {}, "subjects": {}}


def test_load_policy_registry_from_file_valid():
    from src.auth import _load_policy_registry_from_file

    data = {"tenants": {"t2": {}}, "subjects": {}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        path = f.name
    try:
        with patch("src.auth.POLICY_REGISTRY_PATH", path):
            result = _load_policy_registry_from_file()
        assert "t2" in result["tenants"]
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_policy_registry_from_file_invalid_json():
    from src.auth import _load_policy_registry_from_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("bad json")
        path = f.name
    try:
        with patch("src.auth.POLICY_REGISTRY_PATH", path):
            with pytest.raises(RuntimeError, match="valid JSON"):
                _load_policy_registry_from_file()
    finally:
        Path(path).unlink(missing_ok=True)


def test_load_policy_registry_from_file_non_dict():
    from src.auth import _load_policy_registry_from_file

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([1, 2], f)
        path = f.name
    try:
        with patch("src.auth.POLICY_REGISTRY_PATH", path):
            with pytest.raises(RuntimeError, match="must contain a JSON object"):
                _load_policy_registry_from_file()
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# set_policy_registry  (lines 269-302)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_policy_registry_no_path():
    from src.auth import set_policy_registry

    with patch("src.auth.POLICY_REGISTRY_PATH", ""):
        result = await set_policy_registry({"tenants": {"t3": {}}, "subjects": {}})
    assert "t3" in result["tenants"]


@pytest.mark.asyncio
async def test_set_policy_registry_writes_to_disk():
    from src.auth import set_policy_registry

    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "policy.json")
        with patch("src.auth.POLICY_REGISTRY_PATH", path):
            await set_policy_registry({"tenants": {}, "subjects": {"alice": {}}})
        written = json.loads(Path(path).read_text())
    assert "alice" in written["subjects"]


# ---------------------------------------------------------------------------
# validate_security_configuration  (lines 305-335)
# ---------------------------------------------------------------------------


def test_validate_security_config_passes_when_not_public():
    from src.auth import validate_security_configuration

    with patch("src.auth.PUBLIC_EXPOSURE", False):
        validate_security_configuration()  # Should not raise


def test_validate_security_config_raises_no_auth():
    from src.auth import validate_security_configuration

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth.OIDC_ISSUER_URL", ""),
        patch("src.auth.INTERNAL_API_KEY", ""),
        patch("src.auth.LOCAL_DEV_INTERNAL_API_KEY", "dev-default"),
    ):
        with pytest.raises(RuntimeError, match="no auth"):
            validate_security_configuration()


def test_validate_security_config_raises_no_internal_key():
    from src.auth import validate_security_configuration

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth.OIDC_ISSUER_URL", "https://issuer.example.com"),
        patch("src.auth.INTERNAL_API_KEY", ""),
    ):
        with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
            validate_security_configuration()


def test_validate_security_config_raises_dev_default_key():
    from src.auth import validate_security_configuration

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth.OIDC_ISSUER_URL", "https://issuer.example.com"),
        patch("src.auth.INTERNAL_API_KEY", "dev-default"),
        patch("src.auth.LOCAL_DEV_INTERNAL_API_KEY", "dev-default"),
    ):
        with pytest.raises(RuntimeError, match="dev default"):
            validate_security_configuration()


# ---------------------------------------------------------------------------
# get_tenant_id  (lines 352-375)
# ---------------------------------------------------------------------------


def test_get_tenant_id_from_tenant_id_claim():
    from src.auth import get_tenant_id

    assert get_tenant_id({"tenant_id": "t1"}) == "t1"


def test_get_tenant_id_from_tid_claim():
    from src.auth import get_tenant_id

    assert get_tenant_id({"tid": "t2"}) == "t2"


def test_get_tenant_id_from_org_id():
    from src.auth import get_tenant_id

    assert get_tenant_id({"org_id": "org1"}) == "org1"


def test_get_tenant_id_from_namespaced_claim():
    from src.auth import get_tenant_id

    assert get_tenant_id({"https://openbrain/tenant_id": "ns-tenant"}) == "ns-tenant"


def test_get_tenant_id_returns_empty_when_missing():
    from src.auth import get_tenant_id

    assert get_tenant_id({}) == ""


def test_get_tenant_id_skips_non_string_values():
    from src.auth import get_tenant_id

    assert get_tenant_id({"tenant_id": 42}) == ""


# ---------------------------------------------------------------------------
# _claim_values  (lines 378-388)
# ---------------------------------------------------------------------------


def test_claim_values_string_value():
    from src.auth import _claim_values

    result = _claim_values({"roles": "admin user"}, "roles")
    assert "admin" in result
    assert "user" in result


def test_claim_values_list_value():
    from src.auth import _claim_values

    result = _claim_values({"roles": ["admin", "viewer"]}, "roles")
    assert "admin" in result
    assert "viewer" in result


def test_claim_values_comma_separated():
    from src.auth import _claim_values

    result = _claim_values({"roles": "admin,user"}, "roles")
    assert "admin" in result
    assert "user" in result


def test_claim_values_missing_key_returns_empty():
    from src.auth import _claim_values

    assert _claim_values({}, "roles") == []


# ---------------------------------------------------------------------------
# get_domain_scope  (lines 391-426)
# ---------------------------------------------------------------------------


def test_get_domain_scope_read_from_allowed_domains():
    from src.auth import get_domain_scope

    result = get_domain_scope({"allowed_domains": "build personal"}, "read")
    assert "build" in result
    assert "personal" in result


def test_get_domain_scope_write_from_write_domains():
    from src.auth import get_domain_scope

    result = get_domain_scope({"write_domains": ["corporate"]}, "write")
    assert "corporate" in result


def test_get_domain_scope_admin_from_admin_domains():
    from src.auth import get_domain_scope

    result = get_domain_scope({"admin_domains": "build"}, "admin")
    assert "build" in result


def test_get_domain_scope_filters_invalid_domains():
    from src.auth import get_domain_scope

    result = get_domain_scope({"read_domains": "build unknown_domain"}, "read")
    assert "unknown_domain" not in result
    assert "build" in result


def test_get_domain_scope_empty_when_no_matching_claim():
    from src.auth import get_domain_scope

    result = get_domain_scope({}, "read")
    assert result == set()


def test_get_domain_scope_unknown_action_returns_empty():
    from src.auth import get_domain_scope

    result = get_domain_scope({"allowed_domains": "build"}, "delete")
    assert result == set()


# ---------------------------------------------------------------------------
# get_registry_domain_scope  (lines 429-459)
# ---------------------------------------------------------------------------


def test_get_registry_domain_scope_tenant_entry():
    from src.auth import get_registry_domain_scope

    registry = {"tenants": {"t1": {"read_domains": ["build"]}}, "subjects": {}}
    with patch("src.auth.POLICY_REGISTRY", registry):
        result = get_registry_domain_scope("alice", "t1", "read")
    assert "build" in result


def test_get_registry_domain_scope_subject_entry():
    from src.auth import get_registry_domain_scope

    registry = {"tenants": {}, "subjects": {"alice": {"allowed_domains": "personal"}}}
    with patch("src.auth.POLICY_REGISTRY", registry):
        result = get_registry_domain_scope("alice", "", "read")
    assert "personal" in result


def test_get_registry_domain_scope_string_domains():
    from src.auth import get_registry_domain_scope

    registry = {"tenants": {}, "subjects": {"bob": {"read_domains": "build,corporate"}}}
    with patch("src.auth.POLICY_REGISTRY", registry):
        result = get_registry_domain_scope("bob", "", "read")
    assert "build" in result
    assert "corporate" in result


def test_get_registry_domain_scope_non_list_returns_empty():
    from src.auth import get_registry_domain_scope

    registry = {"tenants": {}, "subjects": {"alice": {"read_domains": 42}}}
    with patch("src.auth.POLICY_REGISTRY", registry):
        result = get_registry_domain_scope("alice", "", "read")
    assert result == set()


def test_get_registry_domain_scope_non_dict_entry_returns_empty():
    from src.auth import get_registry_domain_scope

    registry = {"tenants": {}, "subjects": {"alice": "not-a-dict"}}
    with patch("src.auth.POLICY_REGISTRY", registry):
        result = get_registry_domain_scope("alice", "", "read")
    assert result == set()


def test_get_registry_domain_scope_no_subject_or_tenant():
    from src.auth import get_registry_domain_scope

    with patch("src.auth.POLICY_REGISTRY", {"tenants": {}, "subjects": {}}):
        result = get_registry_domain_scope("", "", "read")
    assert result == set()


# ---------------------------------------------------------------------------
# is_privileged_user  (lines 462-501)
# ---------------------------------------------------------------------------


def test_is_privileged_local_dev():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "local-dev"}) is True


def test_is_privileged_internal_via_key():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "internal", "_auth_via_internal_key": True}) is True


def test_is_privileged_internal_without_key_marker_is_not():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "internal"}) is False


def test_is_privileged_admin_role_string():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "user", "roles": "admin"}) is True


def test_is_privileged_admin_role_list():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "user", "roles": ["admin", "viewer"]}) is True


def test_is_privileged_openbrain_admin():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "u", "scope": "openbrain:admin read:all"}) is True


def test_is_privileged_maintain_admin():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "u", "permissions": ["maintain:admin"]}) is True


def test_is_not_privileged_regular_user():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "u", "roles": "viewer"}) is False


def test_is_not_privileged_empty_claims():
    from src.auth import is_privileged_user

    assert is_privileged_user({"sub": "u"}) is False


# ---------------------------------------------------------------------------
# OIDCVerifier  (lines 59-177)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_verifier_metadata_fetches_discovery():
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier("https://issuer.example.com", audience="aud")
    discovery = {
        "issuer": "https://issuer.example.com",
        "authorization_endpoint": "https://issuer.example.com/auth",
        "token_endpoint": "https://issuer.example.com/token",
        "jwks_uri": "https://issuer.example.com/.well-known/jwks.json",
    }
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = discovery

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        metadata = await verifier.metadata()

    assert metadata.issuer == "https://issuer.example.com"
    assert metadata.jwks_uri == "https://issuer.example.com/.well-known/jwks.json"


@pytest.mark.asyncio
async def test_oidc_verifier_metadata_raises_on_failed_discovery():
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier("https://issuer.example.com", audience="aud")

    import httpx

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="OIDC discovery failed"):
            await verifier.metadata()


@pytest.mark.asyncio
async def test_oidc_verifier_metadata_caches():
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier("https://issuer.example.com", audience="aud")
    discovery = {
        "issuer": "https://issuer.example.com",
        "authorization_endpoint": "https://issuer.example.com/auth",
        "token_endpoint": "https://issuer.example.com/token",
        "jwks_uri": "https://issuer.example.com/jwks",
    }
    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = discovery

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        await verifier.metadata()
        await verifier.metadata()  # Second call should use cache

    assert mock_client.get.call_count == 1


@pytest.mark.asyncio
async def test_oidc_verify_token_raises_for_non_jwt():
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier("https://issuer.example.com", audience="aud")
    verifier._metadata = MagicMock()  # Skip discovery
    verifier._metadata_fetched_at = float("inf")

    with pytest.raises(ValueError, match="not a JWT"):
        await verifier.verify_token("not.a.jwt.with.too.many.parts.here")


@pytest.mark.asyncio
async def test_oidc_verify_token_raises_when_no_audience():
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier("https://issuer.example.com", audience="")
    verifier._metadata = MagicMock()
    verifier._metadata_fetched_at = float("inf")
    verifier._jwk_client = MagicMock()
    verifier._jwk_client.get_signing_key_from_jwt = MagicMock(return_value=MagicMock())

    with pytest.raises(ValueError, match="OIDC_AUDIENCE"):
        await verifier.verify_token("header.payload.signature")


# ---------------------------------------------------------------------------
# require_auth  (lines 632-678)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_auth_local_dev_when_not_public():
    from src.auth import require_auth

    request = MagicMock()
    request.headers.get = MagicMock(return_value="")

    with patch("src.auth.PUBLIC_EXPOSURE", False):
        result = await require_auth(request, credentials=None)
    assert result["sub"] == "local-dev"


@pytest.mark.asyncio
async def test_require_auth_accepts_valid_internal_key():
    from src.auth import require_auth

    request = MagicMock()
    request.headers.get = MagicMock(return_value="super-secret-key")
    request.client.host = "127.0.0.1"

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth.INTERNAL_API_KEY", "super-secret-key"),
        patch("src.auth.check_internal_key_rate_limit"),
    ):
        result = await require_auth(request, credentials=None)
    assert result["sub"] == "internal"
    assert result["_auth_via_internal_key"] is True


@pytest.mark.asyncio
async def test_require_auth_rejects_wrong_internal_key():
    from src.auth import require_auth

    request = MagicMock()
    request.headers.get = MagicMock(return_value="wrong-key")

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth.INTERNAL_API_KEY", "correct-key"),
        patch("src.auth._oidc", None),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_auth(request, credentials=None)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_raises_when_no_oidc_and_public():
    from src.auth import require_auth

    request = MagicMock()
    request.headers.get = MagicMock(return_value="")

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth._oidc", None),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_auth(request, credentials=None)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_raises_when_no_credentials():
    from src.auth import require_auth

    request = MagicMock()
    request.headers.get = MagicMock(return_value="")

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth._oidc", MagicMock()),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_auth(request, credentials=None)
        assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_oidc_verify_error_becomes_401():
    from src.auth import require_auth

    request = MagicMock()
    request.headers.get = MagicMock(return_value="")

    mock_oidc = MagicMock()
    mock_oidc.verify_token = AsyncMock(side_effect=ValueError("bad token"))
    credentials = MagicMock()
    credentials.credentials = "header.payload.sig"

    with (
        patch("src.auth.PUBLIC_EXPOSURE", True),
        patch("src.auth._oidc", mock_oidc),
    ):
        with pytest.raises(HTTPException) as exc:
            await require_auth(request, credentials=credentials)
        assert exc.value.status_code == 401
