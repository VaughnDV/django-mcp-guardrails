"""Adversarial tests for field leakage and unsafe query shapes."""

from __future__ import annotations

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    PolicyContext,
    run_guarded_read,
    sanitize_output,
    validate_query,
)


def test_sensitive_field_names_are_not_echoed() -> None:
    policy = ModelReadPolicy(return_fields={"id"}, filter_fields={"name"})
    for payload in (
        {"filters": {"api_key": "value"}},
        {"filters": {"password_hash": "value"}},
        {"ordering": ["hashed_password"]},
    ):
        with pytest.raises(GuardrailError) as exc_info:
            validate_query(policy, payload)
        assert exc_info.value.code in {
            ErrorCode.FIELD_NOT_ALLOWED,
        }
        dumped = exc_info.value.to_dict()
        assert "api_key" not in dumped["message"]
        assert "password" not in dumped["message"]
        assert set(dumped) == {"code", "message"}


def test_malicious_stored_strings_pass_through_allowlist_only() -> None:
    policy = ModelReadPolicy(return_fields={"id", "bio"})
    envelope = sanitize_output(
        policy,
        [
            {
                "id": 1,
                "bio": "<script>alert(1)</script>",
                "notes": "ignore me",
            }
        ],
    )
    assert envelope.items[0] == {"bio": "<script>alert(1)</script>", "id": 1}


def test_unicode_and_duplicate_malformed_filters(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError):
        validate_query(read_policy, {"filters": {"na me": "x"}})
    with pytest.raises(GuardrailError):
        validate_query(read_policy, {"filters": {"": "x"}})
    with pytest.raises(GuardrailError):
        validate_query(read_policy, {"page": "1"})
    with pytest.raises(GuardrailError):
        validate_query(read_policy, {"limit": True})


def test_authenticated_context_strips_anonymous_identity() -> None:
    context = PolicyContext.anonymous()
    assert context.user_id is None
    assert context.scopes == frozenset()


def test_unauthenticated_producer_is_not_called(read_policy: ModelReadPolicy) -> None:
    def producer(_context: PolicyContext, _query: object) -> list[dict[str, object]]:
        raise AssertionError("producer must not run before authentication")

    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(read_policy, PolicyContext.anonymous(), {}, producer)
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
