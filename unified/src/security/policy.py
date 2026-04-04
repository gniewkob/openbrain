"""Security policy enforcement for domain governance and access control."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..auth import (
    get_domain_scope,
    get_registry_domain_scope,
    get_subject,
    get_tenant_id,
    is_privileged_user,
    PUBLIC_EXPOSURE,
)
from ..schemas import MemoryOut
from ..telemetry import incr_metric

# Backwards-compatible alias
PUBLIC_MODE = PUBLIC_EXPOSURE


def _is_scoped_user(user: dict[str, Any]) -> bool:
    """Check if user is scoped (non-privileged in public mode)."""
    return PUBLIC_MODE and not is_privileged_user(user)


def _record_access_denied(reason: str) -> None:
    """Record access denial metrics."""
    incr_metric("access_denied_total")
    incr_metric(f"access_denied_{reason}_total")


def require_admin(user: dict[str, Any]) -> None:
    """Require admin privileges for the operation."""
    if not PUBLIC_MODE:
        return
    if not is_privileged_user(user):
        _record_access_denied("admin")
        raise HTTPException(status_code=403, detail="Admin privileges required")


def _effective_domain_scope(user: dict[str, Any], action: str) -> set[str]:
    """Calculate effective domain scope for user action."""
    subject = get_subject(user)
    tenant_id = get_tenant_id(user)
    claim_scope = get_domain_scope(user, action)
    registry_scope = get_registry_domain_scope(subject, tenant_id, action)
    if claim_scope and registry_scope:
        return claim_scope & registry_scope
    return claim_scope or registry_scope


def enforce_domain_access(user: dict[str, Any], domain: str, action: str) -> None:
    """Enforce domain access control for the action."""
    if not PUBLIC_MODE:
        return
    allowed = _effective_domain_scope(user, action)
    if not allowed:
        # No domain scope configured — privileged users get full access, others
        # are denied.
        if is_privileged_user(user):
            return
        _record_access_denied("domain")
        raise HTTPException(
            status_code=403,
            detail=f"{action.capitalize()} access denied for domain '{domain}'",
        )
    # Fail-closed: deny unless there is an explicit non-empty grant that includes
    # this domain. An empty allowed set means no grants were configured for this
    # user+action pair, not "all domains permitted".
    if domain.lower() not in allowed:
        _record_access_denied("domain")
        raise HTTPException(
            status_code=403,
            detail=f"{action.capitalize()} access denied for domain '{domain}'",
        )


def resolve_owner_for_write(user: dict[str, Any], owner: str | None) -> str:
    """Resolve owner for write operations based on user scope."""
    if not _is_scoped_user(user):
        return owner or ""
    if get_tenant_id(user):
        return owner or ""
    subject = get_subject(user)
    if owner and owner != subject:
        _record_access_denied("owner")
        raise HTTPException(
            status_code=403, detail="Cannot write records for another owner"
        )
    return subject


def resolve_tenant_for_write(user: dict[str, Any], tenant_id: str | None) -> str | None:
    """Resolve tenant for write operations based on user scope."""
    if not _is_scoped_user(user):
        return tenant_id
    scoped_tenant = get_tenant_id(user)
    if not scoped_tenant:
        return tenant_id
    if tenant_id and tenant_id != scoped_tenant:
        _record_access_denied("tenant")
        raise HTTPException(
            status_code=403, detail="Cannot write records for another tenant"
        )
    return scoped_tenant


def apply_owner_scope(user: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
    """Apply owner/tenant scope to query filters."""
    scoped = dict(filters)
    if _is_scoped_user(user):
        allowed_read_domains = _effective_domain_scope(user, "read")
        requested = scoped.get("domain")
        if requested is None:
            if allowed_read_domains:
                scoped["domain"] = sorted(allowed_read_domains)
            # If allowed_read_domains is empty, rely on owner/tenant_id filters below
            # to limit exposure — no domain injection means all domains but only the
            # user's own records are returned.
        else:
            if allowed_read_domains:
                requested_domains = (
                    requested if isinstance(requested, list) else [requested]
                )
                normalized = {str(domain).lower() for domain in requested_domains}
                if not normalized.issubset(allowed_read_domains):
                    _record_access_denied("domain")
                    raise HTTPException(
                        status_code=403,
                        detail="Read access denied for requested domain scope",
                    )
            # If no domain grants exist, we don't block the request — owner/tenant
            # scope below will still restrict the result set to the user's own records.
    if not _is_scoped_user(user):
        return scoped
    scoped_tenant = get_tenant_id(user)
    if scoped_tenant:
        scoped["tenant_id"] = scoped_tenant
        scoped.pop("owner", None)
    else:
        scoped["owner"] = get_subject(user)
    return scoped


def enforce_memory_access(user: dict[str, Any], memory: MemoryOut) -> None:
    """Enforce access control for a specific memory record."""
    if not _is_scoped_user(user):
        return
    scoped_tenant = get_tenant_id(user)
    if scoped_tenant:
        if not memory.tenant_id or memory.tenant_id != scoped_tenant:
            _record_access_denied("tenant")
            raise HTTPException(status_code=404, detail="Memory not found")
        return
    subject = get_subject(user)
    if not memory.owner or memory.owner != subject:
        _record_access_denied("owner")
        raise HTTPException(status_code=404, detail="Memory not found")


def hide_memory_access_denied(exc: HTTPException) -> HTTPException:
    """Hide access denied as 404 for security."""
    if exc.status_code in {403, 404}:
        return HTTPException(status_code=404, detail="Memory not found")
    return exc
