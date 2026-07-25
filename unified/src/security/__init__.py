"""Security, authentication and authorization."""

from .policy import (
    _effective_domain_scope,
    _is_scoped_user,
    _record_access_denied,
    apply_owner_scope,
    enforce_domain_access,
    enforce_memory_access,
    hide_memory_access_denied,
    require_admin,
    resolve_owner_for_write,
    resolve_tenant_for_write,
)

__all__ = [
    "_effective_domain_scope",
    "_is_scoped_user",
    "_record_access_denied",
    "apply_owner_scope",
    "enforce_domain_access",
    "enforce_memory_access",
    "hide_memory_access_denied",
    "require_admin",
    "resolve_owner_for_write",
    "resolve_tenant_for_write",
]
