"""Privacy-safe audit protocol for policy decisions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from django_mcp_guardrails.budgets import filter_digest
from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.errors import ErrorCode, GuardrailError
from django_mcp_guardrails.outputs import ResultEnvelope
from django_mcp_guardrails.queries import NormalizedQuery, query_digest_shape

logger = logging.getLogger("django_mcp_guardrails.audit")


@dataclass(frozen=True, slots=True)
class AuditRecord:
    tool_name: str
    policy_version: str
    user_id: str | int | None
    organization_id: str | int | None
    client_id: str | None
    correlation_id: str | None
    started_at: datetime
    duration_ms: int
    status: str
    error_code: str | None
    row_count: int
    serialized_bytes: int
    truncated: bool
    request_digest: str
    filter_fields: tuple[str, ...] = field(default_factory=tuple)


class AuditBackend(Protocol):
    def record(self, event: AuditRecord) -> None: ...


class LoggingAuditBackend:
    """Structured logs without payloads, prompts, or secrets."""

    def record(self, event: AuditRecord) -> None:
        logger.info(
            "mcp_guardrail",
            extra={
                "tool_name": event.tool_name,
                "policy_version": event.policy_version,
                "user_id": event.user_id,
                "organization_id": event.organization_id,
                "client_id": event.client_id,
                "correlation_id": event.correlation_id,
                "duration_ms": event.duration_ms,
                "status": event.status,
                "error_code": event.error_code,
                "row_count": event.row_count,
                "serialized_bytes": event.serialized_bytes,
                "truncated": event.truncated,
                "request_digest": event.request_digest,
                "filter_fields": list(event.filter_fields),
            },
        )


class DatabaseAuditBackend:
    """Persist audit metadata through the optional AuditEvent model."""

    def record(self, event: AuditRecord) -> None:
        from django_mcp_guardrails.models import AuditEvent

        AuditEvent.objects.create(
            tool_name=event.tool_name,
            policy_version=event.policy_version,
            user_id="" if event.user_id is None else str(event.user_id),
            organization_id=""
            if event.organization_id is None
            else str(event.organization_id),
            client_id=event.client_id or "",
            correlation_id=event.correlation_id or "",
            started_at=event.started_at,
            duration_ms=event.duration_ms,
            status=event.status,
            error_code=event.error_code or "",
            row_count=event.row_count,
            serialized_bytes=event.serialized_bytes,
            truncated=event.truncated,
            request_digest=event.request_digest,
            filter_fields=list(event.filter_fields),
        )


_backend: AuditBackend = LoggingAuditBackend()
_fail_closed = False


def get_audit_backend() -> AuditBackend:
    return _backend


def set_audit_backend(backend: AuditBackend, *, fail_closed: bool = False) -> None:
    global _backend, _fail_closed
    _backend = backend
    _fail_closed = fail_closed


def reset_audit_backend() -> None:
    set_audit_backend(LoggingAuditBackend(), fail_closed=False)


def build_audit_record(
    *,
    tool_name: str,
    policy_version: str,
    context: PolicyContext,
    query: NormalizedQuery | None,
    started_at: datetime,
    duration_ms: int,
    result: ResultEnvelope | None,
    error: GuardrailError | None,
) -> AuditRecord:
    shape = query_digest_shape(query) if query is not None else {}
    raw_filters = shape.get("filters", [])
    filters = raw_filters if isinstance(raw_filters, list) else []
    filter_fields = tuple(
        str(item.get("field"))
        for item in filters
        if isinstance(item, dict) and item.get("field") is not None
    )
    return AuditRecord(
        tool_name=tool_name,
        policy_version=policy_version,
        user_id=context.user_id,
        organization_id=context.organization_id,
        client_id=context.client_id,
        correlation_id=context.correlation_id,
        started_at=started_at,
        duration_ms=duration_ms,
        status="deny" if error is not None else "allow",
        error_code=str(error.code) if error is not None else None,
        row_count=result.meta.count if result is not None else 0,
        serialized_bytes=_serialized_bytes(result),
        truncated=bool(result and result.meta.truncated),
        request_digest=filter_digest(query) if query is not None else "",
        filter_fields=filter_fields,
    )


def emit_audit(event: AuditRecord, *, write_operation: bool = False) -> None:
    """Record an audit event. Reads fail open; required write audits fail closed."""
    try:
        get_audit_backend().record(event)
    except GuardrailError:
        raise
    except Exception:
        logger.exception("Failed to record MCP guardrail audit event")
        if write_operation or _fail_closed:
            raise GuardrailError(
                ErrorCode.PERMISSION_DENIED,
                "The request could not be completed.",
            ) from None


def _serialized_bytes(result: ResultEnvelope | None) -> int:
    if result is None:
        return 0
    return len(
        json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    )
