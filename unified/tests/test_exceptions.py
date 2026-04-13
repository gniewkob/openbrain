"""
Tests for centralized exception handling (ARCH-003).
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status

from src.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseError,
    ErrorContext,
    ExternalServiceError,
    GovernanceError,
    MemoryNotFoundError,
    NotFoundError,
    ObsidianCliError,
    OpenBrainError,
    RateLimitError,
    SyncConflictError,
    ValidationError,
    create_error_response,
    generic_exception_handler,
    http_exception_handler,
    is_production,
    openbrain_exception_handler,
    register_exception_handlers,
    safe_operation,
    value_error_handler,
)


class TestExceptionHierarchy(unittest.TestCase):
    """Test exception hierarchy and attributes."""

    def test_base_error_attributes(self) -> None:
        """Test base OpenBrainError has correct default attributes."""
        exc = OpenBrainError("Test message")
        self.assertEqual(exc.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(exc.error_code, "internal_error")
        self.assertEqual(exc.safe_message, "An internal error occurred")
        self.assertEqual(exc.message, "Test message")

    def test_validation_error(self) -> None:
        """Test ValidationError has correct status code."""
        exc = ValidationError("Invalid input")
        self.assertEqual(exc.status_code, status.HTTP_422_UNPROCESSABLE_CONTENT)
        self.assertEqual(exc.error_code, "validation_error")

    def test_not_found_error(self) -> None:
        """Test NotFoundError has correct status code."""
        exc = NotFoundError("Resource not found")
        self.assertEqual(exc.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(exc.error_code, "not_found")

    def test_memory_not_found_error(self) -> None:
        """Test MemoryNotFoundError inheritance."""
        exc = MemoryNotFoundError("Memory 123 not found")
        self.assertIsInstance(exc, NotFoundError)
        self.assertEqual(exc.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(exc.safe_message, "Memory not found")

    def test_conflict_error(self) -> None:
        """Test ConflictError has correct status code."""
        exc = ConflictError("Duplicate key")
        self.assertEqual(exc.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(exc.error_code, "conflict")

    def test_authentication_error(self) -> None:
        """Test AuthenticationError has correct status code."""
        exc = AuthenticationError("Auth failed")
        self.assertEqual(exc.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(exc.error_code, "authentication_error")

    def test_authorization_error(self) -> None:
        """Test AuthorizationError has correct status code."""
        exc = AuthorizationError("Forbidden")
        self.assertEqual(exc.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(exc.error_code, "authorization_error")

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError has correct status code."""
        exc = RateLimitError("Too many requests")
        self.assertEqual(exc.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(exc.error_code, "rate_limit_exceeded")

    def test_external_service_error(self) -> None:
        """Test ExternalServiceError has correct status code."""
        exc = ExternalServiceError("Service down")
        self.assertEqual(exc.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(exc.error_code, "external_service_error")

    def test_database_error(self) -> None:
        """Test DatabaseError has correct status code."""
        exc = DatabaseError("DB connection failed")
        self.assertEqual(exc.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(exc.error_code, "database_error")

    def test_governance_error(self) -> None:
        """Test GovernanceError has correct status code."""
        exc = GovernanceError("Policy violation")
        self.assertEqual(exc.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(exc.error_code, "governance_violation")

    def test_obsidian_cli_error(self) -> None:
        """Test ObsidianCliError inheritance."""
        exc = ObsidianCliError("CLI failed")
        self.assertIsInstance(exc, ExternalServiceError)
        self.assertEqual(exc.error_code, "external_service_error")

    def test_sync_conflict_error(self) -> None:
        """Test SyncConflictError with extra attributes."""
        exc = SyncConflictError(
            "Conflict detected",
            memory_id="mem_123",
            note_path="vault/note.md",
        )
        self.assertEqual(exc.memory_id, "mem_123")
        self.assertEqual(exc.note_path, "vault/note.md")
        self.assertEqual(exc.status_code, status.HTTP_409_CONFLICT)


class TestErrorResponseCreation(unittest.TestCase):
    """Test error response generation."""

    def test_openbrain_error_response(self) -> None:
        """Test response for OpenBrainError."""
        exc = ValidationError("Invalid field", details={"field": "name"})
        response = create_error_response(exc)
        
        self.assertEqual(response["error"]["code"], "validation_error")
        self.assertIn("message", response["error"])

    def test_unknown_exception_response_development(self) -> None:
        """Test response for unknown exception in development."""
        with patch.dict(os.environ, {"PUBLIC_MODE": ""}):
            exc = ValueError("Something went wrong")
            response = create_error_response(exc)
            
            self.assertEqual(response["error"]["code"], "internal_error")
            self.assertEqual(response["error"]["message"], "Something went wrong")
            self.assertEqual(response["error"]["type"], "ValueError")

    def test_unknown_exception_response_production(self) -> None:
        """Test response for unknown exception in production."""
        with patch.dict(os.environ, {"PUBLIC_MODE": "true"}):
            exc = ValueError("Something went wrong")
            response = create_error_response(exc)
            
            self.assertEqual(response["error"]["code"], "internal_error")
            self.assertEqual(response["error"]["message"], "An internal error occurred")
            self.assertNotIn("type", response["error"])

    def test_sync_conflict_response(self) -> None:
        """Test response includes conflict details."""
        exc = SyncConflictError(
            "Conflict",
            memory_id="mem_123",
            note_path="vault/note.md",
        )
        response = create_error_response(exc)
        
        self.assertEqual(response["error"]["conflict"]["memory_id"], "mem_123")
        self.assertEqual(response["error"]["conflict"]["note_path"], "vault/note.md")


class TestIsProduction(unittest.TestCase):
    """Test production mode detection."""

    def test_is_production_true(self) -> None:
        """Test PUBLIC_MODE=true returns True."""
        with patch.dict(os.environ, {"PUBLIC_MODE": "true"}):
            self.assertTrue(is_production())

    def test_is_production_false(self) -> None:
        """Test PUBLIC_MODE unset returns False."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_production())

    def test_is_production_case_insensitive(self) -> None:
        """Test PUBLIC_MODE is case insensitive."""
        with patch.dict(os.environ, {"PUBLIC_MODE": "TRUE"}):
            self.assertTrue(is_production())


class TestErrorContext(unittest.TestCase):
    """Test ErrorContext context manager."""

    def test_context_manager_no_error(self) -> None:
        """Test context manager with no error."""
        with ErrorContext("test operation", ValidationError):
            pass  # No error

    def test_context_manager_converts_exception(self) -> None:
        """Test context manager converts generic exception."""
        with self.assertRaises(DatabaseError) as ctx:
            with ErrorContext("database query", DatabaseError):
                raise ValueError("Connection refused")
        
        self.assertIn("database query failed", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, ValueError)

    def test_context_manager_preserves_openbrain_error(self) -> None:
        """Test context manager doesn't wrap OpenBrainError."""
        with self.assertRaises(ValidationError):
            with ErrorContext("operation", DatabaseError):
                raise ValidationError("Already specific")


class TestExceptionHandlers(unittest.IsolatedAsyncioTestCase):
    """Test FastAPI exception handlers."""

    async def test_openbrain_exception_handler(self) -> None:
        """Test handler returns JSONResponse."""
        mock_request = MagicMock()
        exc = ValidationError("Invalid input")
        
        response = await openbrain_exception_handler(mock_request, exc)
        
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_CONTENT)
        self.assertIn("error", response.body.decode())

    async def test_generic_exception_handler_openbrain(self) -> None:
        """Test generic handler with OpenBrainError."""
        mock_request = MagicMock()
        exc = NotFoundError("Not found")
        
        response = await generic_exception_handler(mock_request, exc)
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    async def test_generic_exception_handler_http_exception(self) -> None:
        """Test generic handler with HTTPException."""
        mock_request = MagicMock()
        exc = HTTPException(status_code=418, detail="I'm a teapot")
        
        response = await generic_exception_handler(mock_request, exc)
        
        self.assertEqual(response.status_code, 418)

    async def test_generic_exception_handler_generic(self) -> None:
        """Test generic handler with generic exception."""
        mock_request = MagicMock()
        exc = RuntimeError("Unexpected")
        
        response = await generic_exception_handler(mock_request, exc)
        
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class TestHttpExceptionHandlerBranches(unittest.IsolatedAsyncioTestCase):
    """Cover uncovered branches in http_exception_handler."""

    async def test_string_detail_sets_message(self) -> None:
        """detail is str → message = detail (lines 282-283)."""
        mock_request = MagicMock()
        exc = HTTPException(status_code=400, detail="bad request string")
        response = await http_exception_handler(mock_request, exc)
        import json
        body = json.loads(response.body)
        assert body["error"]["message"] == "bad request string"

    async def test_non_dict_non_str_detail_uses_status_code(self) -> None:
        """detail is neither dict nor str → message = str(exc.status_code) (line 287)."""
        mock_request = MagicMock()
        exc = HTTPException(status_code=404, detail=["list", "detail"])
        response = await http_exception_handler(mock_request, exc)
        import json
        body = json.loads(response.body)
        assert body["error"]["message"] == "404"


class TestValueErrorHandler(unittest.IsolatedAsyncioTestCase):
    """Cover value_error_handler (lines 307-308)."""

    async def test_value_error_handler_returns_422(self) -> None:
        mock_request = MagicMock()
        exc = ValueError("bad value")
        response = await value_error_handler(mock_request, exc)
        assert response.status_code == 422

    async def test_value_error_handler_production_uses_generic_message(self) -> None:
        mock_request = MagicMock()
        exc = ValueError("sensitive detail")
        with patch("src.exceptions.is_production", return_value=True):
            response = await value_error_handler(mock_request, exc)
        import json
        body = json.loads(response.body)
        assert body["error"]["message"] == "Invalid request"


class TestRegisterExceptionHandlers(unittest.TestCase):
    """Cover register_exception_handlers type check (line 343)."""

    def test_raises_type_error_for_non_fastapi(self) -> None:
        with self.assertRaises(TypeError, msg="app must be a FastAPI instance"):
            register_exception_handlers("not-a-fastapi-app")


class TestSafeOperation(unittest.TestCase):
    """Cover safe_operation decorator (lines 373-385)."""

    def test_safe_operation_re_raises_openbrain_error(self) -> None:
        """OpenBrainError is re-raised as-is, not wrapped."""
        with self.assertRaises(ValidationError):
            safe_operation("test op", ValidationError)(
                lambda: (_ for _ in ()).throw(ValidationError("already specific"))
            )()

    def test_safe_operation_converts_generic_exception(self) -> None:
        """Generic exception is wrapped in the specified error_class."""
        with self.assertRaises(DatabaseError):
            safe_operation("db op", DatabaseError)(
                lambda: (_ for _ in ()).throw(RuntimeError("db fail"))
            )()


if __name__ == "__main__":
    unittest.main()
