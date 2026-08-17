"""Evaluate a registered policy without talking to an MCP framework."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.errors import ErrorCode, GuardrailError, safe_error
from django_mcp_guardrails.orm import fetch_serialized_rows
from django_mcp_guardrails.outputs import ResultEnvelope, sanitize_output
from django_mcp_guardrails.policies import (
    ModelReadPolicy,
    Policy,
    RiskLevel,
    WritePolicy,
)
from django_mcp_guardrails.queries import NormalizedQuery, validate_query
from django_mcp_guardrails.registry import PolicyRegistry, get_registry

Producer = Callable[[PolicyContext, NormalizedQuery], object]


def execute_guarded(
    name: str,
    context: PolicyContext,
    raw_query: Mapping[str, Any] | NormalizedQuery | None,
    producer: Producer,
    *,
    registry: PolicyRegistry | None = None,
) -> ResultEnvelope:
    """Look up a policy, validate the query, run producer, and sanitize output."""
    active_registry = registry if registry is not None else get_registry()
    policy = active_registry.get(name)
    return run_guarded_read(policy, context, raw_query, producer)


def execute_model_read(
    policy: ModelReadPolicy,
    context: PolicyContext,
    raw_query: Mapping[str, Any] | NormalizedQuery | None,
) -> ResultEnvelope:
    """Apply a model read policy to a scoped QuerySet and sanitize the result."""
    return run_guarded_read(
        policy,
        context,
        raw_query,
        lambda trusted, normalized: fetch_serialized_rows(policy, trusted, normalized),
    )


def run_guarded_read(
    policy: Policy | WritePolicy,
    context: PolicyContext,
    raw_query: Mapping[str, Any] | NormalizedQuery | None,
    producer: Producer,
) -> ResultEnvelope:
    """Validate, produce, and sanitize a read result."""
    if isinstance(policy, WritePolicy) or policy.risk is not RiskLevel.READ:
        raise safe_error(ErrorCode.PERMISSION_DENIED)
    if not context.is_authenticated:
        raise safe_error(ErrorCode.UNAUTHENTICATED)
    if not policy.enabled:
        raise safe_error(ErrorCode.PERMISSION_DENIED)
    try:
        query = validate_query(policy, raw_query)
        items = producer(context, query)
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes, Mapping)):
            raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)
        return sanitize_output(policy, items, query=query)
    except GuardrailError:
        raise
    except Exception:
        raise GuardrailError(
            ErrorCode.OUTPUT_SCHEMA_VIOLATION,
            "The request could not be completed.",
        ) from None
