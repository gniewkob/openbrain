"""Tests for src/security/policy.py — domain access enforcement and scoping."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from src.schemas import MemoryOut
from src.security.policy import (
    apply_owner_scope,
    enforce_domain_access,
    enforce_memory_access,
    hide_memory_access_denied,
    require_admin,
    resolve_owner_for_write,
    resolve_tenant_for_write,
)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _memory_out(**kwargs):
    defaults = {
        "id": "m1",
        "domain": "build",
        "entity_type": "Note",
        "content": "c",
        "owner": "alice",
        "status": "active",
        "version": 1,
        "sensitivity": "internal",
        "tags": [],
        "created_at": _NOW,
        "updated_at": _NOW,
        "created_by": "alice",
    }
    defaults.update(kwargs)
    return MemoryOut(**defaults)


class SecurityPolicyTests(unittest.TestCase):
    """Unified unit test suite for src/security/policy.py (Domain Access and Scoping)."""

    def _patch_auth(
        self,
        public=True,
        privileged=False,
        subject="alice",
        tenant_id=None,
        domain_scope=None,
        registry_scope=None,
    ):
        """Helper to create nested mocks for policy auth checks."""
        return (
            patch("src.security.policy.PUBLIC_MODE", public),
            patch("src.security.policy.PUBLIC_EXPOSURE", public),
            patch("src.security.policy.is_privileged_user", return_value=privileged),
            patch("src.security.policy.get_subject", return_value=subject),
            patch("src.security.policy.get_tenant_id", return_value=tenant_id),
            patch("src.security.policy.get_domain_scope", return_value=domain_scope),
            patch(
                "src.security.policy.get_registry_domain_scope",
                return_value=registry_scope,
            ),
            patch("src.security.policy.incr_metric"),
            patch("src.auth.PUBLIC_EXPOSURE", public),
        )

    # ---------------------------------------------------------------------------
    # require_admin
    # ---------------------------------------------------------------------------

    def test_require_admin_passes_when_public_mode_off(self):
        with patch("src.security.policy.PUBLIC_EXPOSURE", False):
            require_admin({})  # Should not raise

    def test_require_admin_passes_privileged_user(self):
        patches = self._patch_auth(public=True, privileged=True)
        with (
            patches[1],
            patches[2],
            patch("src.auth.PUBLIC_EXPOSURE", True),
        ):
            require_admin({})  # Should not raise

    def test_require_admin_raises_403_for_unprivileged(self):
        patches = self._patch_auth(public=True, privileged=False)
        with (
            patches[1],
            patches[2],
            patches[7],
            patch("src.auth.PUBLIC_EXPOSURE", True),
        ):
            with self.assertRaises(HTTPException) as exc:
                require_admin({})
            self.assertEqual(exc.exception.status_code, 403)

    # ---------------------------------------------------------------------------
    # enforce_domain_access
    # ---------------------------------------------------------------------------

    def _check_enforce_domain_access(
        self,
        user,
        domain,
        action,
        public=True,
        privileged=False,
        subject="alice",
        tenant_id=None,
        domain_scope=None,
        registry_scope=None,
        should_raise=False,
        expected_status=403,
        expected_msg_part=None,
    ):
        p_mode, p_exp, p_priv, p_sub, p_ten, p_dom, p_reg, p_metric, p_auth_exp = (
            self._patch_auth(
                public=public,
                privileged=privileged,
                subject=subject,
                tenant_id=tenant_id,
                domain_scope=domain_scope,
                registry_scope=registry_scope,
            )
        )

        with (
            p_mode,
            p_exp,
            p_priv,
            p_sub,
            p_ten,
            p_dom,
            p_reg,
            p_metric,
            p_auth_exp,
        ):
            if should_raise:
                with self.assertRaises(HTTPException) as ctx:
                    enforce_domain_access(user, domain, action)
                self.assertEqual(ctx.exception.status_code, expected_status)
                if expected_msg_part:
                    self.assertIn(expected_msg_part, ctx.exception.detail)
            else:
                enforce_domain_access(user, domain, action)

    def test_enforce_domain_access_skips_when_not_public(self):
        self._check_enforce_domain_access(
            user={}, domain="build", action="read", public=False
        )

    def test_enforce_domain_access_privileged_no_scope_allowed(self):
        self._check_enforce_domain_access(
            user={},
            domain="build",
            action="read",
            public=True,
            privileged=True,
            domain_scope=None,
            registry_scope=None,
            should_raise=False,
        )

    def test_enforce_domain_access_unprivileged_no_scope_raises(self):
        self._check_enforce_domain_access(
            user={},
            domain="build",
            action="read",
            public=True,
            privileged=False,
            domain_scope=None,
            registry_scope=None,
            should_raise=True,
            expected_status=403,
            expected_msg_part="Read access denied for domain 'build'",
        )

    def test_enforce_domain_access_domain_in_scope_passes(self):
        self._check_enforce_domain_access(
            user={},
            domain="build",
            action="read",
            public=True,
            privileged=False,
            domain_scope={"build"},
            registry_scope=None,
            should_raise=False,
        )

    def test_enforce_domain_access_domain_not_in_scope_raises(self):
        self._check_enforce_domain_access(
            user={},
            domain="build",
            action="read",
            public=True,
            privileged=False,
            domain_scope={"corporate"},
            registry_scope=None,
            should_raise=True,
            expected_status=403,
            expected_msg_part="Read access denied for domain 'build'",
        )

    def test_enforce_domain_access_intersection_of_scopes(self):
        self._check_enforce_domain_access(
            user={},
            domain="build",
            action="read",
            public=True,
            privileged=False,
            domain_scope={"build", "corporate"},
            registry_scope={"build"},
            should_raise=False,
        )

    def test_enforce_domain_access_case_insensitive_passes(self):
        self._check_enforce_domain_access(
            user={},
            domain="BUILD",
            action="read",
            public=True,
            privileged=False,
            domain_scope={"build"},
            registry_scope=None,
            should_raise=False,
        )

    def test_enforce_domain_access_error_message_capitalizes_action(self):
        self._check_enforce_domain_access(
            user={},
            domain="build",
            action="write",
            public=True,
            privileged=False,
            domain_scope={"corporate"},
            registry_scope=None,
            should_raise=True,
            expected_status=403,
            expected_msg_part="Write access denied for domain 'build'",
        )

    def test_enforce_domain_access_empty_domain_passes_if_in_scope(self):
        self._check_enforce_domain_access(
            user={},
            domain="",
            action="read",
            public=True,
            privileged=False,
            domain_scope={""},
            registry_scope=None,
            should_raise=False,
        )

    def test_enforce_domain_access_fail_closed_on_empty_allowed_set(self):
        # Empty set means no grants configured for this user+action
        self._check_enforce_domain_access(
            user={},
            domain="personal",
            action="delete",
            public=True,
            privileged=False,
            domain_scope=set(),
            registry_scope=set(),
            should_raise=True,
            expected_status=403,
            expected_msg_part="Delete access denied for domain 'personal'",
        )

    def test_enforce_domain_access_special_characters_in_domain(self):
        self._check_enforce_domain_access(
            user={},
            domain="custom-domain_123",
            action="read",
            public=True,
            privileged=False,
            domain_scope={"custom-domain_123"},
            registry_scope=None,
            should_raise=False,
        )

    def test_enforce_domain_access_extremely_large_scope(self):
        large_scope = {f"domain-{i}" for i in range(1000)}
        self._check_enforce_domain_access(
            user={},
            domain="domain-999",
            action="read",
            public=True,
            privileged=False,
            domain_scope=large_scope,
            registry_scope=None,
            should_raise=False,
        )

    # ---------------------------------------------------------------------------
    # resolve_owner_for_write
    # ---------------------------------------------------------------------------

    def test_resolve_owner_not_scoped_returns_provided_owner(self):
        patches = self._patch_auth(public=False)
        with patches[0], patches[1], patches[2]:
            result = resolve_owner_for_write({}, "bob")
        self.assertEqual(result, "bob")

    def test_resolve_owner_not_scoped_returns_empty_when_none(self):
        patches = self._patch_auth(public=False)
        with patches[0], patches[1], patches[2]:
            result = resolve_owner_for_write({}, None)
        self.assertEqual(result, "")

    def test_resolve_owner_scoped_with_tenant_passes_through(self):
        patches = self._patch_auth(
            public=True, privileged=False, subject="alice", tenant_id="t1"
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = resolve_owner_for_write({}, "someone")
        self.assertEqual(result, "someone")

    def test_resolve_owner_scoped_no_tenant_sets_subject(self):
        patches = self._patch_auth(
            public=True, privileged=False, subject="alice", tenant_id=None
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = resolve_owner_for_write({}, None)
        self.assertEqual(result, "alice")

    def test_resolve_owner_scoped_different_owner_raises(self):
        patches = self._patch_auth(
            public=True, privileged=False, subject="alice", tenant_id=None
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[7],
        ):
            with self.assertRaises(HTTPException) as exc:
                resolve_owner_for_write({}, "bob")
            self.assertEqual(exc.exception.status_code, 403)

    def test_resolve_owner_scoped_with_tenant_different_owner_passes(self):
        patches = self._patch_auth(
            public=True, privileged=False, subject="alice", tenant_id="t1"
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = resolve_owner_for_write({}, "bob")
        self.assertEqual(result, "bob")

    # ---------------------------------------------------------------------------
    # resolve_tenant_for_write
    # ---------------------------------------------------------------------------

    def test_resolve_tenant_not_scoped_returns_provided(self):
        patches = self._patch_auth(public=False)
        with patches[0], patches[1], patches[2]:
            result = resolve_tenant_for_write({}, "t1")
        self.assertEqual(result, "t1")

    def test_resolve_tenant_scoped_no_tenant_returns_provided(self):
        patches = self._patch_auth(public=True, privileged=False, tenant_id=None)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = resolve_tenant_for_write({}, "t2")
        self.assertEqual(result, "t2")

    def test_resolve_tenant_scoped_matches_returns_scoped(self):
        patches = self._patch_auth(public=True, privileged=False, tenant_id="t1")
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = resolve_tenant_for_write({}, "t1")
        self.assertEqual(result, "t1")

    def test_resolve_tenant_scoped_mismatch_raises(self):
        patches = self._patch_auth(public=True, privileged=False, tenant_id="t1")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[7],
        ):
            with self.assertRaises(HTTPException) as exc:
                resolve_tenant_for_write({}, "t2")
            self.assertEqual(exc.exception.status_code, 403)

    # ---------------------------------------------------------------------------
    # apply_owner_scope
    # ---------------------------------------------------------------------------

    def test_apply_owner_scope_not_scoped_returns_unchanged(self):
        patches = self._patch_auth(public=False)
        with patches[0], patches[1], patches[2]:
            result = apply_owner_scope({}, {"domain": "build"})
        self.assertEqual(result, {"domain": "build"})

    def test_apply_owner_scope_scoped_no_tenant_injects_owner(self):
        patches = self._patch_auth(
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
        self.assertEqual(result["owner"], "alice")

    def test_apply_owner_scope_scoped_with_tenant_injects_tenant(self):
        patches = self._patch_auth(
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
        self.assertEqual(result["tenant_id"], "t1")
        self.assertNotIn("owner", result)

    def test_apply_owner_scope_domain_not_subset_raises(self):
        patches = self._patch_auth(
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
            with self.assertRaises(HTTPException) as exc:
                apply_owner_scope({}, {"domain": "build"})
            self.assertEqual(exc.exception.status_code, 403)

    def test_apply_owner_scope_injects_allowed_domains_when_no_request(self):
        patches = self._patch_auth(
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
        self.assertEqual(set(result["domain"]), {"build", "personal"})

    # ---------------------------------------------------------------------------
    # enforce_memory_access
    # ---------------------------------------------------------------------------

    def test_enforce_memory_access_not_scoped_passes(self):
        patches = self._patch_auth(public=False)
        with patches[0], patches[1], patches[2]:
            enforce_memory_access({}, _memory_out())  # No raise

    def test_enforce_memory_access_tenant_matches_passes(self):
        patches = self._patch_auth(public=True, privileged=False, tenant_id="t1")
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            enforce_memory_access({}, _memory_out(tenant_id="t1"))  # No raise

    def test_enforce_memory_access_tenant_mismatch_raises_404(self):
        patches = self._patch_auth(public=True, privileged=False, tenant_id="t1")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[7],
        ):
            with self.assertRaises(HTTPException) as exc:
                enforce_memory_access({}, _memory_out(tenant_id="t2"))
            self.assertEqual(exc.exception.status_code, 404)

    def test_enforce_memory_access_tenant_missing_raises_404(self):
        patches = self._patch_auth(public=True, privileged=False, tenant_id="t1")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[7],
        ):
            with self.assertRaises(HTTPException) as exc:
                enforce_memory_access({}, _memory_out(tenant_id=None))
            self.assertEqual(exc.exception.status_code, 404)

    def test_enforce_memory_access_owner_matches_passes(self):
        patches = self._patch_auth(
            public=True, privileged=False, subject="alice", tenant_id=None
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            enforce_memory_access({}, _memory_out(owner="alice"))  # No raise

    def test_enforce_memory_access_owner_mismatch_raises_404(self):
        patches = self._patch_auth(
            public=True, privileged=False, subject="alice", tenant_id=None
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[7],
        ):
            with self.assertRaises(HTTPException) as exc:
                enforce_memory_access({}, _memory_out(owner="bob"))
            self.assertEqual(exc.exception.status_code, 404)

    # ---------------------------------------------------------------------------
    # hide_memory_access_denied
    # ---------------------------------------------------------------------------

    def test_hide_403_as_404(self):
        exc = HTTPException(status_code=403, detail="Forbidden")
        result = hide_memory_access_denied(exc)
        self.assertEqual(result.status_code, 404)

    def test_hide_404_stays_404(self):
        exc = HTTPException(status_code=404, detail="Not found")
        result = hide_memory_access_denied(exc)
        self.assertEqual(result.status_code, 404)

    def test_hide_500_unchanged(self):
        exc = HTTPException(status_code=500, detail="Server error")
        result = hide_memory_access_denied(exc)
        self.assertEqual(result.status_code, 500)


if __name__ == "__main__":
    unittest.main()
