"""
Central exception hierarchy for OpenBrain (ARCH-003).

Provides unified error handling with:
- Domain-specific exception types
- Automatic HTTP status code mapping
- Structured error responses
- Safe error messages in production
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


# =============================================================================
# Base Exception Hierarchy
# =============================================================================


class OpenBrainError(Exception):
    """Base exception for all OpenBrain errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    safe_message: str = "An internal error occurred"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ):
        self.message = message or self.safe_message
        self.details = details or {}
        self.cause = cause
        super().__init__(self.message)


class ValidationError(OpenBrainError):
    """Invalid input data."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"
    safe_message = "Invalid input data"


class NotFoundError(OpenBrainError):
    """Resource not found."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"
    safe_message = "Resource not found"


class ConflictError(OpenBrainError):
    """Resource conflict (e.g., duplicate key)."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"
    safe_message = "Resource conflict"


class AuthenticationError(OpenBrainError):
    """Authentication failed."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_error"
    safe_message = "Authentication required"


class AuthorizationError(OpenBrainError):
    """Permission denied."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "authorization_error"
    safe_message = "Permission denied"


class RateLimitError(OpenBrainError):
    """Rate limit exceeded."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"
    safe_message = "Rate limit exceeded, please try again later"


class ExternalServiceError(OpenBrainError):
    """External service failure (Obsidian CLI, Ollama, etc.)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "external_service_error"
    safe_message = "External service unavailable"


class DatabaseError(OpenBrainError):
    """Database operation failed."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "database_error"
    safe_message = "Database operation failed"


class GovernanceError(OpenBrainError):
    """Domain governance policy violation."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "governance_violation"
    safe_message = "Operation violates domain governance policy"


# =============================================================================
# Specific Exception Types
# =============================================================================


class MemoryNotFoundError(NotFoundError):
    """Memory record not found."""

    safe_message = "Memory not found"


class VaultNotFoundError(NotFoundError):
    """Obsidian vault not found."""

    safe_message = "Vault not found"


class NoteNotFoundError(NotFoundError):
    """Obsidian note not found."""

    safe_message = "Note not found"


class DuplicateKeyError(ConflictError):
    """Unique constraint violation."""

    safe_message = "Resource with this key already exists"


class ObsidianCliError(ExternalServiceError):
    """Obsidian CLI command failed."""

    safe_message = "Obsidian CLI operation failed"


class EmbeddingError(ExternalServiceError):
    """Embedding generation failed."""

    safe_message = "Failed to generate embedding"


class SyncConflictError(ConflictError):
    """Bidirectional sync conflict."""

    safe_message = "Sync conflict detected"

    def __init__(
        self,
        message: str | None = None,
        *,
        memory_id: str | None = None,
        note_path: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details=details)
        self.memory_id = memory_id
        self.note_path = note_path


# =============================================================================
# Error Response Models
# =============================================================================


def is_production() -> bool:
    """Check if running in production mode."""
    return os.environ.get("PUBLIC_MODE", "").lower() == "true"


_HTTP_STATUS_TO_CODE: dict[int, str] = {
    400: "validation_error",
    401: "auth_required",
    403: "access_denied",
    404: "memory_not_found",
    409: "match_key_conflict",
    422: "semantic_error",
    429: "rate_limit_exceeded",
    503: "backend_unavailable",
}

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset([429, 503])


def create_error_response(
    exc: Exception,
    request: Request | None = None,
) -> dict[str, Any]:
    """Create standardized error response."""

    if isinstance(exc, OpenBrainError):
        retryable = exc.status_code in _RETRYABLE_STATUS_CODES
        response: dict[str, Any] = {
            "error": {
                "code": exc.error_code,
                "message": exc.safe_message if is_production() else exc.message,
                "retryable": retryable,
            }
        }

        # Add details for specific error types (safe to expose)
        if exc.details and not is_production():
            response["error"]["details"] = exc.details

        # Add sync conflict details
        if isinstance(exc, SyncConflictError):
            response["error"]["conflict"] = {
                "memory_id": exc.memory_id,
                "note_path": exc.note_path,
            }

        return response

    # Unknown exception - hide details in production
    if is_production():
        return {
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred",
                "retryable": False,
            }
        }

    # Development - show full error
    return {
        "error": {
            "code": "internal_error",
            "message": str(exc),
            "type": type(exc).__name__,
            "retryable": False,
        }
    }


# =============================================================================
# Exception Handlers
# =============================================================================


async def openbrain_exception_handler(
    request: Request,
    exc: OpenBrainError,
) -> JSONResponse:
    """Handler for OpenBrain exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(exc, request),
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Wrap all HTTPException into ErrorDetail envelope with semantic code.

    Maps HTTP status code to a domain-specific error code. Adds retryable:true
    for 429 and 503 responses.
    """
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, "internal_error")
    retryable = exc.status_code in _RETRYABLE_STATUS_CODES

    # If detail is already an ErrorDetail envelope (e.g. raised internally),
    # extract the code and message rather than clobbering them.
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = detail["code"]
        message = detail.get("message", str(exc.status_code))
    elif isinstance(detail, str):
        message = detail
    else:
        message = str(exc.status_code)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": None,
                "retryable": retryable,
            }
        },
    )


async def value_error_handler(
    request: Request,
    exc: ValueError,
) -> JSONResponse:
    """Map ValueError from business logic to 422 semantic_error."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "semantic_error",
                "message": str(exc),
                "details": None,
                "retryable": False,
            }
        },
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handler for unhandled exceptions."""
    response = create_error_response(exc, request)

    if isinstance(exc, OpenBrainError):
        status_code = exc.status_code
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    return JSONResponse(status_code=status_code, content=response)


def register_exception_handlers(app: Any) -> None:
    """Register all exception handlers with FastAPI app."""
    from fastapi import FastAPI

    if not isinstance(app, FastAPI):
        raise TypeError("app must be a FastAPI instance")

    # Most-specific handlers first
    app.add_exception_handler(OpenBrainError, openbrain_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ValueError, value_error_handler)

    # Generic handler for unexpected exceptions
    app.add_exception_handler(Exception, generic_exception_handler)


# =============================================================================
# Utility Functions for Safe Error Handling
# =============================================================================


def safe_operation(
    operation: str,
    error_class: type[OpenBrainError] = OpenBrainError,
    **error_kwargs: Any,
) -> Any:
    """
    Decorator/context manager pattern for safe operation execution.

    Usage:
        result = safe_operation("database query", DatabaseError)(
            lambda: db.query(...)
        )
    """

    def wrapper(func: Any) -> Any:
        try:
            return func()
        except OpenBrainError:
            raise
        except Exception as e:
            raise error_class(
                f"{operation} failed: {e}",
                cause=e,
                **error_kwargs,
            ) from e

    return wrapper


class ErrorContext:
    """Context manager for safe error handling with context."""

    def __init__(
        self,
        operation: str,
        error_class: type[OpenBrainError] = OpenBrainError,
        **error_kwargs: Any,
    ):
        self.operation = operation
        self.error_class = error_class
        self.error_kwargs = error_kwargs

    def __enter__(self) -> ErrorContext:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if exc_val is not None and not isinstance(exc_val, OpenBrainError):
            raise self.error_class(
                f"{self.operation} failed: {exc_val}",
                cause=exc_val,
                **self.error_kwargs,
            ) from exc_val
        return False  # Don't suppress the exception if it's already OpenBrainError
