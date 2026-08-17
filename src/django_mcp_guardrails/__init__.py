"""Deny-by-default policy and output protection for Django MCP tools."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.decorators import guarded_tool
from django_mcp_guardrails.engine import execute_guarded, run_guarded_read
from django_mcp_guardrails.errors import ErrorCode, GuardrailError
from django_mcp_guardrails.outputs import ResultEnvelope, sanitize_output
from django_mcp_guardrails.policies import (
    ModelReadPolicy,
    RiskLevel,
    ToolPolicy,
    WritePolicy,
)
from django_mcp_guardrails.queries import FilterClause, NormalizedQuery, validate_query
from django_mcp_guardrails.registry import PolicyRegistry, get_registry, reset_registry
from django_mcp_guardrails.schemas import generate_input_schema, generate_output_schema

try:
    __version__ = version("django-mcp-guardrails")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.1.0"

__all__ = [
    "ErrorCode",
    "FilterClause",
    "GuardrailError",
    "ModelReadPolicy",
    "NormalizedQuery",
    "PolicyContext",
    "PolicyRegistry",
    "ResultEnvelope",
    "RiskLevel",
    "ToolPolicy",
    "WritePolicy",
    "__version__",
    "execute_guarded",
    "generate_input_schema",
    "generate_output_schema",
    "get_registry",
    "guarded_tool",
    "reset_registry",
    "run_guarded_read",
    "sanitize_output",
    "validate_query",
]
