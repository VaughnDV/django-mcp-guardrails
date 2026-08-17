"""Adapter for django-mcp-server.

Framework imports are isolated so the core package remains installable
without this extra. django-mcp-server 0.5.x requires the MCP Python SDK 1.x
(FastMCP). MCP SDK 2.x is rejected with a clear error.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib.metadata import PackageNotFoundError, version
from typing import Any, cast

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.engine import execute_model_read
from django_mcp_guardrails.errors import ErrorCode, GuardrailError
from django_mcp_guardrails.policies import ModelReadPolicy
from django_mcp_guardrails.registry import get_registry
from django_mcp_guardrails.schemas import (
    envelope_matches_schema,
    generate_output_schema,
)

_MIN_FRAMEWORK = (0, 5, 7)
_MAX_FRAMEWORK = (0, 6, 0)

OrganizationGetter = Callable[[object], Any]
ClientGetter = Callable[[object], str | None]
ScopeGetter = Callable[[object], Iterable[str]]


class AdapterUnavailable(RuntimeError):
    """Raised when django-mcp-server or a compatible MCP SDK is missing."""


class MCPGuardrailError(Exception):
    """MCP-facing tool error that carries a stable guardrail code."""

    def __init__(self, error: GuardrailError) -> None:
        super().__init__(error.message)
        self.code = error.code
        self.error = error

    def to_mcp_payload(self) -> dict[str, str]:
        return {"code": str(self.code), "message": str(self)}


def assert_supported_django_mcp_server() -> str:
    """Return the installed framework version or raise AdapterUnavailable."""
    try:
        installed = version("django-mcp-server")
    except PackageNotFoundError as exc:
        raise AdapterUnavailable(
            "Install django-mcp-guardrails[django-mcp-server] to use this adapter."
        ) from exc
    parsed = _parse_version(installed)
    if parsed < _MIN_FRAMEWORK or parsed >= _MAX_FRAMEWORK:
        raise AdapterUnavailable(
            f"django-mcp-server {installed} is not supported. "
            "Use django-mcp-server 0.5.x."
        )
    try:
        from mcp.server import FastMCP  # noqa: F401
    except ImportError as exc:
        raise AdapterUnavailable(
            "django-mcp-server 0.5.x requires the MCP Python SDK 1.x (FastMCP). "
            "MCP SDK 2.x is not compatible."
        ) from exc
    return installed


def _import_django_mcp() -> tuple[Any, Any]:
    """Import django-mcp-server without failing on FastMCP settings warnings."""
    import warnings

    warning_cls: type[Warning]
    try:
        from pydantic_settings.exceptions import IncompleteFieldDefinitionWarning

        warning_cls = IncompleteFieldDefinitionWarning
    except ImportError:  # pragma: no cover
        warning_cls = UserWarning
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", warning_cls)
        from mcp_server.djangomcp import django_request_ctx, global_mcp_server
    return django_request_ctx, global_mcp_server


def register_guarded_model_tool(
    *,
    policy: ModelReadPolicy,
    name: str,
    description: str | None = None,
    mcp_server: Any | None = None,
    get_organization_id: OrganizationGetter | None = None,
    get_client_id: ClientGetter | None = None,
    get_scopes: ScopeGetter | None = None,
) -> Callable[..., dict[str, Any]]:
    """Register a policy-backed read tool with django-mcp-server.

    Tool arguments are treated as an untrusted query. Identity comes from
    ``django_request_ctx`` via ``PolicyContext.from_request``.
    """
    assert_supported_django_mcp_server()
    django_request_ctx, global_mcp_server = _import_django_mcp()

    server = mcp_server if mcp_server is not None else global_mcp_server
    registry = get_registry()
    if not registry.contains(name):
        registry.register(name, policy)

    safe_description = description or (
        "Read records allowed by the server policy. Results are bounded and field-filtered."
    )

    def tool(query: dict[str, Any] | None = None) -> dict[str, Any]:
        request = django_request_ctx.get(None)
        if request is None:
            raise MCPGuardrailError(GuardrailError(ErrorCode.UNAUTHENTICATED))
        context = PolicyContext.from_request(
            request,
            get_organization_id=get_organization_id,
            get_client_id=get_client_id,
            get_scopes=get_scopes,
        )
        try:
            envelope = execute_model_read(policy, context, query or {})
        except GuardrailError as exc:
            raise MCPGuardrailError(exc) from None
        if not envelope_matches_schema(envelope, generate_output_schema(policy)):
            raise MCPGuardrailError(GuardrailError(ErrorCode.OUTPUT_SCHEMA_VIOLATION))
        return envelope.to_dict()

    tool.__name__ = name
    tool.__doc__ = safe_description
    tool.guardrail_policy = policy  # type: ignore[attr-defined]
    tool.guardrail_name = name  # type: ignore[attr-defined]
    add_tool = getattr(server, "add_tool", None)
    if callable(add_tool):
        add_tool(tool, name=name, description=safe_description)
    return tool


def current_django_request() -> object | None:
    """Return the request stored by django-mcp-server, if any."""
    assert_supported_django_mcp_server()
    django_request_ctx, _global_mcp_server = _import_django_mcp()

    return cast(object | None, django_request_ctx.get(None))


def _parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in value.split("."):
        digits = "".join(character for character in item if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)
