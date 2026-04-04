"""Security, authentication and authorization."""
from .policy import (
    enforce_domain_access,
    enforce_memory_access,
    require_admin,
    resolve_owner_for_write,
    resolve_tenant_for_write,
    apply_owner_scope,
    hide_memory_access_denied,
    _is_scoped_user,
    _effective_domain_scope,
    _record_access_denied,
)

__all__ = [
    "enforce_domain_access",
    "enforce_memory_access",
    "require_admin",
    "resolve_owner_for_write",
    "resolve_tenant_for_write",
    "apply_owner_scope",
    "hide_memory_access_denied",
    "_is_scoped_user",
    "_effective_domain_scope",
    "_record_access_denied",
]
