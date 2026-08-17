"""Privacy-safe audit recording and failure-policy tests."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    PolicyContext,
    ToolPolicy,
    run_guarded_read,
)
from django_mcp_guardrails.audit import (
    AuditRecord,
    DatabaseAuditBackend,
    emit_audit,
    reset_audit_backend,
    set_audit_backend,
)
from django_mcp_guardrails.models import AuditEvent


class RecordingAuditBackend:
    def __init__(self) -> None:
        self.events: list[AuditRecord] = []

    def record(self, event: AuditRecord) -> None:
        self.events.append(event)


class FailingAuditBackend:
    def record(self, event: AuditRecord) -> None:
        raise RuntimeError("cannot persist audit")


def test_successful_reads_emit_redacted_allow_records() -> None:
    backend = RecordingAuditBackend()
    set_audit_backend(backend)
    policy = ModelReadPolicy(
        return_fields={"id", "name"},
        filter_fields={"name"},
        lookups={"name": {"exact"}},
    )
    envelope = run_guarded_read(
        policy,
        PolicyContext.authenticated("user-1", organization_id="org-9"),
        {"filters": {"name": "super-secret-token"}},
        lambda _context, _query: [{"id": 1, "name": "Acme", "password": "nope"}],
        tool_name="search_items",
    )
    assert envelope.meta.count == 1
    assert len(backend.events) == 1
    event = backend.events[0]
    dumped = asdict(event)
    assert event.status == "allow"
    assert event.error_code is None
    assert event.tool_name == "search_items"
    assert event.filter_fields == ("name",)
    assert "super-secret-token" not in str(dumped)
    assert "nope" not in str(dumped)
    assert event.request_digest
    assert event.serialized_bytes > 0
    assert event.duration_ms >= 0


def test_denials_are_audited_without_running_the_producer() -> None:
    backend = RecordingAuditBackend()
    set_audit_backend(backend)

    def producer(_context: PolicyContext, _query: object) -> list[dict[str, object]]:
        raise AssertionError("producer must not run")

    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(
            ModelReadPolicy(return_fields={"id"}),
            PolicyContext.anonymous(),
            {},
            producer,
            tool_name="search_items",
        )
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
    assert backend.events[0].status == "deny"
    assert backend.events[0].error_code == ErrorCode.UNAUTHENTICATED


def test_audit_false_skips_recording() -> None:
    backend = RecordingAuditBackend()
    set_audit_backend(backend)
    policy = ToolPolicy(return_fields={"id"}, audit=False)
    run_guarded_read(
        policy,
        PolicyContext.authenticated("user-1"),
        {},
        lambda _context, _query: [{"id": 1}],
        tool_name="ping",
    )
    assert backend.events == []


def test_read_audit_failure_fails_open() -> None:
    set_audit_backend(FailingAuditBackend())
    envelope = run_guarded_read(
        ModelReadPolicy(return_fields={"id"}),
        PolicyContext.authenticated("user-1"),
        {},
        lambda _context, _query: [{"id": 1}],
        tool_name="search_items",
    )
    assert envelope.items == ({"id": 1},)


def test_fail_closed_audit_denies_the_request() -> None:
    set_audit_backend(FailingAuditBackend(), fail_closed=True)
    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(
            ModelReadPolicy(return_fields={"id"}),
            PolicyContext.authenticated("user-1"),
            {},
            lambda _context, _query: [{"id": 1}],
            tool_name="search_items",
        )
    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_write_audit_failure_fails_closed() -> None:
    set_audit_backend(FailingAuditBackend())
    event = AuditRecord(
        tool_name="update_item",
        policy_version="2026-08-01",
        user_id="user-1",
        organization_id=None,
        client_id=None,
        correlation_id=None,
        started_at=datetime.now(UTC),
        duration_ms=1,
        status="deny",
        error_code=str(ErrorCode.PERMISSION_DENIED),
        row_count=0,
        serialized_bytes=0,
        truncated=False,
        request_digest="",
    )
    with pytest.raises(GuardrailError) as exc_info:
        emit_audit(event, write_operation=True)
    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


@pytest.mark.django_db
def test_database_backend_stores_metadata_not_payloads() -> None:
    set_audit_backend(DatabaseAuditBackend())
    run_guarded_read(
        ModelReadPolicy(
            return_fields={"id", "name"},
            filter_fields={"name"},
        ),
        PolicyContext.authenticated("user-1", organization_id="org-1"),
        {"filters": {"name": "hidden-value"}},
        lambda _context, _query: [{"id": 1, "name": "Acme"}],
        tool_name="search_items",
    )
    stored = AuditEvent.objects.get()
    assert stored.tool_name == "search_items"
    assert stored.status == "allow"
    assert stored.filter_fields == ["name"]
    assert "hidden-value" not in stored.request_digest
    assert stored.row_count == 1
    reset_audit_backend()
