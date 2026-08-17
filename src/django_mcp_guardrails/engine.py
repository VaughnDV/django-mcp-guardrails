"""Evaluate a registered policy without talking to an MCP framework."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from django_mcp_guardrails.audit import build_audit_record, emit_audit
from django_mcp_guardrails.budgets import enforce_budgets
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
    return run_guarded_read(policy, context, raw_query, producer, tool_name=name)


def execute_model_read(
    policy: ModelReadPolicy,
    context: PolicyContext,
    raw_query: Mapping[str, Any] | NormalizedQuery | None,
    *,
    tool_name: str = "model_read",
) -> ResultEnvelope:
    """Apply a model read policy to a scoped QuerySet and sanitize the result."""
    return run_guarded_read(
        policy,
        context,
        raw_query,
        lambda trusted, normalized: fetch_serialized_rows(policy, trusted, normalized),
        tool_name=tool_name,
    )


def run_guarded_read(
    policy: Policy | WritePolicy,
    context: PolicyContext,
    raw_query: Mapping[str, Any] | NormalizedQuery | None,
    producer: Producer,
    *,
    tool_name: str = "tool",
) -> ResultEnvelope:
    """Validate, produce, sanitize, enforce budgets, and audit a read result."""
    started_at = datetime.now(UTC)
    started = monotonic()
    query: NormalizedQuery | None = None
    result: ResultEnvelope | None = None
    error: GuardrailError | None = None
    try:
        if isinstance(policy, WritePolicy) or policy.risk is not RiskLevel.READ:
            raise safe_error(ErrorCode.PERMISSION_DENIED)
        if not context.is_authenticated:
            raise safe_error(ErrorCode.UNAUTHENTICATED)
        if not policy.enabled:
            raise safe_error(ErrorCode.PERMISSION_DENIED)
        try:
            query = validate_query(policy, raw_query)
            items = producer(context, query)
            if not isinstance(items, Sequence) or isinstance(
                items, (str, bytes, Mapping)
            ):
                raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)
            result = sanitize_output(policy, items, query=query)
            enforce_budgets(
                policy,
                context,
                query,
                tool_name=tool_name,
                row_count=result.meta.count,
            )
            return result
        except GuardrailError:
            raise
        except Exception:
            raise GuardrailError(
                ErrorCode.OUTPUT_SCHEMA_VIOLATION,
                "The request could not be completed.",
            ) from None
    except GuardrailError as exc:
        error = exc
        raise
    finally:
        duration_ms = int((monotonic() - started) * 1000)
        if getattr(policy, "audit", True):
            emit_audit(
                build_audit_record(
                    tool_name=tool_name,
                    policy_version=getattr(policy, "version", ""),
                    context=context,
                    query=query,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    result=result,
                    error=error,
                )
            )
