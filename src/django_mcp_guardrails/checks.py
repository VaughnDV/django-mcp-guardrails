"""Django system checks for incomplete or unsafe MCP policies."""

from __future__ import annotations

from collections.abc import Sequence

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, Warning, register

from django_mcp_guardrails.policies import ModelReadPolicy, WritePolicy
from django_mcp_guardrails.registry import get_registry

_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "passwd",
        "hashed_password",
        "password_hash",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
        "api_key",
        "private_key",
    }
)
_MAX_SAFE_LIMIT = 1000
_MAX_SAFE_RELATION_DEPTH = 2


def check_policies(
    app_configs: Sequence[AppConfig] | None = None, **kwargs: object
) -> list[CheckMessage]:
    """Inspect registered policies. Does not query the database."""
    messages: list[CheckMessage] = []
    if getattr(settings, "MCP_GUARDRAILS_AUDIT_STORE_PAYLOADS", False):
        messages.append(
            Error(
                "Audit configuration stores payloads.",
                hint="Disable MCP_GUARDRAILS_AUDIT_STORE_PAYLOADS; record metadata only.",
                id="django_mcp_guardrails.E006",
            )
        )
    registry = get_registry()
    if len(registry) == 0:
        messages.append(
            Warning(
                "No MCP guardrail policies are registered.",
                hint="Register explicit policies before exposing tools.",
                id="django_mcp_guardrails.W001",
            )
        )
    for name, policy in registry.items():
        if isinstance(policy, WritePolicy) or getattr(policy, "risk", None) == "write":
            messages.append(
                Error(
                    f"Write policy {name!r} is not allowed in this version.",
                    id="django_mcp_guardrails.E001",
                    obj=name,
                )
            )
            continue
        if not isinstance(policy, ModelReadPolicy):
            continue
        messages.extend(_check_model_read_policy(name, policy))
    return messages


def _check_model_read_policy(name: str, policy: ModelReadPolicy) -> list[CheckMessage]:
    messages: list[CheckMessage] = []
    if not policy.return_fields:
        messages.append(
            Error(
                f"Policy {name!r} has an empty return_fields allowlist.",
                hint="An empty allowlist grants no fields. Declare explicit output fields.",
                id="django_mcp_guardrails.E002",
                obj=name,
            )
        )
    if policy.max_limit > _MAX_SAFE_LIMIT:
        messages.append(
            Error(
                f"Policy {name!r} has an unbounded max_limit.",
                hint=f"Keep max_limit at {_MAX_SAFE_LIMIT} or below unless a dedicated export channel exists.",
                id="django_mcp_guardrails.E003",
                obj=name,
            )
        )
    if policy.max_relation_depth > _MAX_SAFE_RELATION_DEPTH:
        messages.append(
            Error(
                f"Policy {name!r} allows unrestricted relation traversal.",
                id="django_mcp_guardrails.E004",
                obj=name,
            )
        )
    if policy.queryset is None:
        messages.append(
            Warning(
                f"Policy {name!r} has no scoped queryset callable.",
                hint="Provide a queryset factory that applies tenant scope first.",
                id="django_mcp_guardrails.W002",
                obj=name,
            )
        )
    sensitive = sorted(
        field
        for field in policy.return_fields
        if field.lower() in _SENSITIVE_FIELD_NAMES
    )
    if sensitive:
        messages.append(
            Error(
                f"Policy {name!r} allowlists sensitive field types.",
                hint="Remove secret, token, and password fields from return_fields.",
                id="django_mcp_guardrails.E005",
                obj=name,
            )
        )
    return messages


_registered = False


def register_checks() -> None:
    global _registered
    if _registered:
        return
    register(check_policies, Tags.security)
    _registered = True
