"""Decorator, engine, and exception-sanitization tests."""

from __future__ import annotations

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    PolicyContext,
    WritePolicy,
    execute_guarded,
    get_registry,
    guarded_tool,
    run_guarded_read,
)


def test_guarded_tool_registers_and_sanitizes(read_policy: ModelReadPolicy) -> None:
    @guarded_tool(policy=read_policy, risk="read")
    def search_sponsors(
        _context: PolicyContext, _query: object
    ) -> list[dict[str, object]]:
        return [
            {"id": 1, "name": "Acme", "password": "nope", "extra": True},
            {"id": 2, "name": "Beta"},
        ]

    result = search_sponsors(
        PolicyContext.authenticated("user-1"),
        {"filters": {"name": "Acme"}, "limit": 10},
    )
    assert get_registry().contains("search_sponsors")
    assert result.items[0] == {"id": 1, "name": "Acme"}
    assert "password" not in result.items[0]


def test_unauthenticated_context_is_denied(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(
            read_policy,
            PolicyContext.anonymous(),
            {},
            lambda _context, _query: [],
        )
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED


def test_producer_exception_does_not_leak_secrets(read_policy: ModelReadPolicy) -> None:
    def producer(_context: PolicyContext, _query: object) -> list[dict[str, object]]:
        raise RuntimeError("password=supersecret token=abcd")

    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(
            read_policy,
            PolicyContext.authenticated("user-1"),
            {},
            producer,
        )
    assert exc_info.value.code is ErrorCode.OUTPUT_SCHEMA_VIOLATION
    assert "supersecret" not in exc_info.value.message
    assert "password" not in exc_info.value.message
    assert exc_info.value.message == "The request could not be completed."


def test_write_decorator_is_disabled() -> None:
    with pytest.raises(GuardrailError) as exc_info:

        @guarded_tool(policy=WritePolicy(), name="update_sponsor")
        def update_sponsor(
            _context: PolicyContext, _query: object
        ) -> list[dict[str, object]]:
            return []

    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_execute_guarded_uses_registry(read_policy: ModelReadPolicy) -> None:
    get_registry().register("search_sponsors", read_policy)
    envelope = execute_guarded(
        "search_sponsors",
        PolicyContext.authenticated("user-1", organization_id="org-1"),
        {"limit": 1},
        lambda _context, _query: [{"id": 1, "name": "Acme"}, {"id": 2, "name": "Beta"}],
    )
    assert envelope.meta.count == 1
    assert envelope.meta.has_more is True


def test_risk_mismatch_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(ValueError, match="risk"):

        @guarded_tool(policy=read_policy, risk="write")
        def search_sponsors(
            _context: PolicyContext, _query: object
        ) -> list[dict[str, object]]:
            return []
