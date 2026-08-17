"""Reusable adapter contract tests. Each MCP adapter must satisfy this suite."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.errors import ErrorCode
from django_mcp_guardrails.outputs import ResultEnvelope


class AdapterDriver(Protocol):
    """Minimal surface used by the shared contract tests."""

    def list_tool_names(self) -> list[str]: ...

    def call(
        self,
        name: str,
        context: PolicyContext,
        arguments: Mapping[str, Any],
    ) -> ResultEnvelope | dict[str, Any]: ...

    def call_raw(
        self,
        name: str,
        context: PolicyContext,
        arguments: Mapping[str, Any],
    ) -> Any: ...


def assert_tools_are_listed_deterministically(driver: AdapterDriver) -> None:
    names = driver.list_tool_names()
    assert names == sorted(names)
    assert names


def assert_unauthenticated_is_denied(
    driver: AdapterDriver,
    name: str,
    anonymous: PolicyContext,
) -> None:
    try:
        driver.call(name, anonymous, {})
    except Exception as exc:
        payload = getattr(exc, "to_mcp_payload", None)
        if callable(payload):
            data = payload()
            assert data["code"] in {
                str(ErrorCode.UNAUTHENTICATED),
                str(ErrorCode.PERMISSION_DENIED),
            }
            assert "password" not in data["message"]
            return
        raise AssertionError("Adapter must raise a structured MCP error") from exc
    raise AssertionError("Unauthenticated calls must not succeed")


def assert_output_is_bounded_and_sanitized(
    driver: AdapterDriver,
    name: str,
    context: PolicyContext,
) -> None:
    result = driver.call(name, context, {"limit": 1})
    payload = result.to_dict() if isinstance(result, ResultEnvelope) else result
    assert set(payload) <= {"items", "meta"}
    assert payload["meta"]["limit"] == 1
    for item in payload["items"]:
        assert "secret_note" not in item
        assert "password" not in item
