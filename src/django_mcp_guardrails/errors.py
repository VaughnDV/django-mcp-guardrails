"""Stable error codes and safe messages for policy denials."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable, public error codes returned to MCP clients."""

    FIELD_NOT_ALLOWED = "field_not_allowed"
    RELATION_NOT_ALLOWED = "relation_not_allowed"
    LOOKUP_NOT_ALLOWED = "lookup_not_allowed"
    LIMIT_EXCEEDED = "limit_exceeded"
    SESSION_BUDGET_EXCEEDED = "session_budget_exceeded"
    BULK_EXPORT_BLOCKED = "bulk_export_blocked"
    PERMISSION_DENIED = "permission_denied"
    OUTPUT_SCHEMA_VIOLATION = "output_schema_violation"
    INVALID_QUERY = "invalid_query"
    UNAUTHENTICATED = "unauthenticated"


SAFE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.FIELD_NOT_ALLOWED: "A requested field is not allowed.",
    ErrorCode.RELATION_NOT_ALLOWED: "A requested relation is not allowed.",
    ErrorCode.LOOKUP_NOT_ALLOWED: "A requested lookup is not allowed.",
    ErrorCode.LIMIT_EXCEEDED: "The requested limit is not allowed.",
    ErrorCode.SESSION_BUDGET_EXCEEDED: "The session export budget has been exceeded.",
    ErrorCode.BULK_EXPORT_BLOCKED: "Bulk export is not allowed for this collection.",
    ErrorCode.PERMISSION_DENIED: "This request is not permitted.",
    ErrorCode.OUTPUT_SCHEMA_VIOLATION: "The tool result did not match the output policy.",
    ErrorCode.INVALID_QUERY: "The query is not valid.",
    ErrorCode.UNAUTHENTICATED: "Authentication is required.",
}


class GuardrailError(Exception):
    """Policy denial or validation failure with a stable public code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message or SAFE_MESSAGES[code]
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        """Return a client-safe error payload. Hidden field names are omitted."""
        return {"code": str(self.code), "message": self.message}


def safe_error(code: ErrorCode) -> GuardrailError:
    """Build an error that never interpolates untrusted or hidden names."""
    return GuardrailError(code)
