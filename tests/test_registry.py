"""Registry and missing-policy fail-closed tests."""

from __future__ import annotations

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    PolicyContext,
    PolicyRegistry,
    WritePolicy,
    execute_guarded,
    get_registry,
)
from django_mcp_guardrails.policies import RiskLevel, ToolPolicy


def test_missing_policy_fails_closed() -> None:
    registry = PolicyRegistry()
    with pytest.raises(GuardrailError) as exc_info:
        registry.get("search_sponsors")
    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED
    assert "search_sponsors" not in exc_info.value.message
    assert "Sponsor" not in exc_info.value.message


def test_empty_registry_grants_nothing() -> None:
    assert len(get_registry()) == 0
    with pytest.raises(GuardrailError) as exc_info:
        execute_guarded(
            "anything",
            PolicyContext.authenticated("user-1"),
            {},
            lambda _context, _query: [],
        )
    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_duplicate_registration_is_rejected(read_policy: ModelReadPolicy) -> None:
    registry = PolicyRegistry()
    registry.register("search_sponsors", read_policy)
    with pytest.raises(ValueError):
        registry.register("search_sponsors", read_policy)


def test_names_are_sorted(read_policy: ModelReadPolicy) -> None:
    registry = PolicyRegistry()
    registry.register("zeta", read_policy)
    registry.register("alpha", read_policy)
    assert registry.names() == ("alpha", "zeta")


def test_write_policy_cannot_be_registered() -> None:
    registry = PolicyRegistry()
    policy = WritePolicy()
    with pytest.raises(GuardrailError) as exc_info:
        registry.register("update_sponsor", policy)
    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_enabled_write_policy_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="disabled"):
        WritePolicy(enabled=True)


def test_unknown_risk_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown risk"):
        ToolPolicy(risk="explode")  # type: ignore[arg-type]


def test_tool_policy_risk_values() -> None:
    policy = ToolPolicy(risk=RiskLevel.READ, return_fields={"ok"})
    assert policy.risk is RiskLevel.READ
