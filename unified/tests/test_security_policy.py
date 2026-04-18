"""Tests for src/security/policy.py — domain access enforcement and scoping."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from src.security.policy import (
    apply_owner_scope,
    enforce_domain_access,
    enforce_memory_access,
    hide_memory_access_denied,
    require_admin,
    resolve_owner_for_write,
    resolve_tenant_for_write,
)
from src.schemas import MemoryOut

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _user(subject="alice", tenant_id=None, privileged=False, domain_scope=None):
    return {
        "_subject": subject,
        "_tenant_id": tenant_id,
        "_privileged": privileged,
        "_domain_scope": domain_scope or set(),
    }


def _memory_out(**kwargs):
    defaults = dict(
        id="m1",
        domain="build",
        entity_type="Note",
        content="c",
        owner="alice",
        status="active",
        version=1,
        sensitivity="internal",
        tags=[],
        created_at=_NOW,
        updated_at=_NOW,
        created_by="alice",
    )
    defaults.update(kwargs)
    return MemoryOut(**defaults)


def _patch_auth(
    public=True,
    privileged=False,
    subject="alice",
    tenant_id=None,
    domain_scope=None,
    registry_scope=None,
):
    """Patch PUBLIC_MODE and auth helpers used by policy.py.

    Note: PUBLIC_MODE is a module-level alias captured at import time, so we
    patch it directly rather than patching PUBLIC_EXPOSURE.
    """
    return [
        patch("src.security.policy.PUBLIC_MODE", public),  # [0]
        patch("src.security.policy.PUBLIC_EXPOSURE", public),  # [1]
        patch("src.security.policy.is_privileged_user", return_value=privileged),  # [2]
        patch("src.security.policy.get_subject", return_value=subject),  # [3]
        patch("src.security.policy.get_tenant_id", return_value=tenant_id),  # [4]
        patch("src.security.policy.get_domain_scope", return_value=domain_scope),  # [5]
        patch(
            "src.security.policy.get_registry_domain_scope", return_value=registry_scope
        ),  # [6]
        patch("src.security.policy.incr_metric"),  # [7]
    ]


# ---------------------------------------------------------------------------
# require_admin
# ---------------------------------------------------------------------------


def test_require_admin_passes_when_public_mode_off():
    with patch("src.security.policy.PUBLIC_EXPOSURE", False):
        require_admin({})  # Should not raise


def test_require_admin_passes_privileged_user():
    patches = _patch_auth(public=True, privileged=True)
    with patches[1], patches[2], patch("src.auth.PUBLIC_EXPOSURE", True):
        require_admin({})  # Should not raise


def test_require_admin_raises_403_for_unprivileged():
    patches = _patch_auth(public=True, privileged=False)
    with patches[1], patches[2], patches[7], patch("src.auth.PUBLIC_EXPOSURE", True):
        with pytest.raises(HTTPException) as exc:
            require_admin({})
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# enforce_domain_access
# ---------------------------------------------------------------------------


def test_enforce_domain_access_skips_when_not_public():
    with patch("src.security.policy.PUBLIC_EXPOSURE", False):
        enforce_domain_access({}, "build", "read")  # No raise


def _enforce_patches(public=True, **kwargs):
    """Convenience: all patches needed for enforce_domain_access."""
    ps = _patch_auth(public=public, **kwargs)
    return ps + [patch("src.auth.PUBLIC_EXPOSURE", public)]


def test_enforce_domain_access_privileged_no_scope_allowed():
    ps = _enforce_patches(privileged=True, domain_scope=None, registry_scope=None)
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        enforce_domain_access({}, "build", "read")  # Privileged → pass


def test_enforce_domain_access_unprivileged_no_scope_raises():
    ps = _enforce_patches(privileged=False, domain_scope=None, registry_scope=None)
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        with pytest.raises(HTTPException) as exc:
            enforce_domain_access({}, "build", "read")
        assert exc.value.status_code == 403


def test_enforce_domain_access_domain_in_scope_passes():
    ps = _enforce_patches(privileged=False, domain_scope={"build"}, registry_scope=None)
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        enforce_domain_access({}, "build", "read")  # No raise


def test_enforce_domain_access_domain_not_in_scope_raises():
    ps = _enforce_patches(
        privileged=False, domain_scope={"corporate"}, registry_scope=None
    )
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        with pytest.raises(HTTPException) as exc:
            enforce_domain_access({}, "build", "read")
        assert exc.value.status_code == 403


def test_enforce_domain_access_intersection_of_scopes():
    ps = _enforce_patches(
        privileged=False, domain_scope={"build", "corporate"}, registry_scope={"build"}
    )
    with ps[0], ps[1], ps[2], ps[3], ps[4], ps[5], ps[6], ps[7], ps[8]:
        enforce_domain_access({}, "build", "read")  # build in intersection → pass


# ---------------------------------------------------------------------------
# resolve_owner_for_write
# ---------------------------------------------------------------------------


def test_resolve_owner_not_scoped_returns_provided_owner():
    patches = _patch_auth(public=False)
    with patches[0], patches[1], patches[2]:
        result = resolve_owner_for_write({}, "bob")
    assert result == "bob"


def test_resolve_owner_not_scoped_returns_empty_when_none():
    patches = _patch_auth(public=False)
    with patches[0], patches[1], patches[2]:
        result = resolve_owner_for_write({}, None)
    assert result == ""


def test_resolve_owner_scoped_with_tenant_passes_through():
    patches = _patch_auth(
        public=True, privileged=False, subject="alice", tenant_id="t1"
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = resolve_owner_for_write({}, "someone")
    assert result == "someone"


def test_resolve_owner_scoped_no_tenant_sets_subject():
    patches = _patch_auth(
        public=True, privileged=False, subject="alice", tenant_id=None
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = resolve_owner_for_write({}, None)
    assert result == "alice"


def test_resolve_owner_scoped_different_owner_raises():
    patches = _patch_auth(
        public=True, privileged=False, subject="alice", tenant_id=None
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[7]:
        with pytest.raises(HTTPException) as exc:
            resolve_owner_for_write({}, "bob")
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# resolve_tenant_for_write
# ---------------------------------------------------------------------------


def test_resolve_tenant_not_scoped_returns_provided():
    patches = _patch_auth(public=False)
    with patches[0], patches[1], patches[2]:
        result = resolve_tenant_for_write({}, "t1")
    assert result == "t1"


def test_resolve_tenant_scoped_no_tenant_returns_provided():
    patches = _patch_auth(public=True, privileged=False, tenant_id=None)
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = resolve_tenant_for_write({}, "t2")
    assert result == "t2"


def test_resolve_tenant_scoped_matches_returns_scoped():
    patches = _patch_auth(public=True, privileged=False, tenant_id="t1")
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        result = resolve_tenant_for_write({}, "t1")
    assert result == "t1"


def test_resolve_tenant_scoped_mismatch_raises():
    patches = _patch_auth(public=True, privileged=False, tenant_id="t1")
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[7]:
        with pytest.raises(HTTPException) as exc:
            resolve_tenant_for_write({}, "t2")
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# apply_owner_scope
# ---------------------------------------------------------------------------


def test_apply_owner_scope_not_scoped_returns_unchanged():
    patches = _patch_auth(public=False)
    with patches[0], patches[1], patches[2]:
        result = apply_owner_scope({}, {"domain": "build"})
    assert result == {"domain": "build"}


def test_apply_owner_scope_scoped_no_tenant_injects_owner():
    patches = _patch_auth(
        public=True,
        privileged=False,
        subject="alice",
        tenant_id=None,
        domain_scope=None,
        registry_scope=None,
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        result = apply_owner_scope({}, {})
    assert result["owner"] == "alice"


def test_apply_owner_scope_scoped_with_tenant_injects_tenant():
    patches = _patch_auth(
        public=True,
        privileged=False,
        subject="alice",
        tenant_id="t1",
        domain_scope=None,
        registry_scope=None,
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        result = apply_owner_scope({}, {})
    assert result["tenant_id"] == "t1"
    assert "owner" not in result


def test_apply_owner_scope_domain_not_subset_raises():
    patches = _patch_auth(
        public=True,
        privileged=False,
        subject="alice",
        tenant_id=None,
        domain_scope={"corporate"},
        registry_scope=None,
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        with pytest.raises(HTTPException) as exc:
            apply_owner_scope({}, {"domain": "build"})
        assert exc.value.status_code == 403


def test_apply_owner_scope_injects_allowed_domains_when_no_request():
    patches = _patch_auth(
        public=True,
        privileged=False,
        subject="alice",
        tenant_id=None,
        domain_scope={"build", "personal"},
        registry_scope=None,
    )
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        result = apply_owner_scope({}, {})
    assert set(result["domain"]) == {"build", "personal"}


# ---------------------------------------------------------------------------
# enforce_memory_access
# ---------------------------------------------------------------------------


def test_enforce_memory_access_not_scoped_passes():
    patches = _patch_auth(public=False)
    with patches[0], patches[1], patches[2]:
        enforce_memory_access({}, _memory_out())  # No raise


def test_enforce_memory_access_tenant_matches_passes():
    patches = _patch_auth(public=True, privileged=False, tenant_id="t1")
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        enforce_memory_access({}, _memory_out(tenant_id="t1"))  # No raise


def test_enforce_memory_access_tenant_mismatch_raises_404():
    patches = _patch_auth(public=True, privileged=False, tenant_id="t1")
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[7]:
        with pytest.raises(HTTPException) as exc:
            enforce_memory_access({}, _memory_out(tenant_id="t2"))
        assert exc.value.status_code == 404


def test_enforce_memory_access_tenant_missing_raises_404():
    patches = _patch_auth(public=True, privileged=False, tenant_id="t1")
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[7]:
        with pytest.raises(HTTPException) as exc:
            enforce_memory_access({}, _memory_out(tenant_id=None))
        assert exc.value.status_code == 404


def test_enforce_memory_access_owner_matches_passes():
    patches = _patch_auth(
        public=True, privileged=False, subject="alice", tenant_id=None
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4]:
        enforce_memory_access({}, _memory_out(owner="alice"))  # No raise


def test_enforce_memory_access_owner_mismatch_raises_404():
    patches = _patch_auth(
        public=True, privileged=False, subject="alice", tenant_id=None
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[7]:
        with pytest.raises(HTTPException) as exc:
            enforce_memory_access({}, _memory_out(owner="bob"))
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# hide_memory_access_denied
# ---------------------------------------------------------------------------


def test_hide_403_as_404():
    exc = HTTPException(status_code=403, detail="Forbidden")
    result = hide_memory_access_denied(exc)
    assert result.status_code == 404


def test_hide_404_stays_404():
    exc = HTTPException(status_code=404, detail="Not found")
    result = hide_memory_access_denied(exc)
    assert result.status_code == 404


def test_hide_500_unchanged():
    exc = HTTPException(status_code=500, detail="Server error")
    result = hide_memory_access_denied(exc)
    assert result.status_code == 500
