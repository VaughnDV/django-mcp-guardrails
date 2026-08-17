"""Decorators that attach policies to application tool callables."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.engine import run_guarded_read
from django_mcp_guardrails.errors import ErrorCode, safe_error
from django_mcp_guardrails.orm import fetch_serialized_rows
from django_mcp_guardrails.outputs import ResultEnvelope
from django_mcp_guardrails.policies import (
    ModelReadPolicy,
    Policy,
    RiskLevel,
    WritePolicy,
)
from django_mcp_guardrails.queries import NormalizedQuery
from django_mcp_guardrails.registry import PolicyRegistry, get_registry

F = TypeVar("F", bound=Callable[..., Any])


def guarded_tool(
    *,
    policy: Policy | WritePolicy,
    risk: str | RiskLevel | None = None,
    name: str | None = None,
    registry: PolicyRegistry | None = None,
) -> Callable[[F], F]:
    """Register a policy and wrap a producer that returns serialized mappings.

    The wrapped function receives a trusted ``PolicyContext`` and a validated
    ``NormalizedQuery``. Its return value is sanitized before it is returned.
    """
    if isinstance(policy, WritePolicy):
        policy.assert_disabled()
    declared_risk = _coerce_optional_risk(risk)
    if declared_risk is not None and declared_risk is not policy.risk:
        raise ValueError("Decorator risk must match the policy risk.")
    if policy.risk is not RiskLevel.READ:
        raise safe_error(ErrorCode.PERMISSION_DENIED)

    def decorator(fn: F) -> F:
        tool_name = name or fn.__name__
        active_registry = registry if registry is not None else get_registry()
        active_registry.register(tool_name, policy)

        @wraps(fn)
        def wrapper(
            context: PolicyContext,
            query: dict[str, Any] | NormalizedQuery | None = None,
            *args: Any,
            **kwargs: Any,
        ) -> ResultEnvelope:
            def producer(
                trusted_context: PolicyContext, normalized: NormalizedQuery
            ) -> object:
                if isinstance(policy, ModelReadPolicy) and policy.queryset is not None:
                    return fetch_serialized_rows(policy, trusted_context, normalized)
                return fn(trusted_context, normalized, *args, **kwargs)

            return run_guarded_read(policy, context, query, producer)

        wrapper.guardrail_policy = policy  # type: ignore[attr-defined]
        wrapper.guardrail_name = tool_name  # type: ignore[attr-defined]
        return cast(F, wrapper)

    return decorator


def _coerce_optional_risk(value: str | RiskLevel | None) -> RiskLevel | None:
    if value is None:
        return None
    return value if isinstance(value, RiskLevel) else RiskLevel(value)
