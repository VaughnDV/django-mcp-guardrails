"""Deny-by-default registry of guarded tools and model policies."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from django_mcp_guardrails.errors import ErrorCode, safe_error
from django_mcp_guardrails.policies import (
    Policy,
    WritePolicy,
)


class PolicyRegistry:
    """In-memory registry. Missing names fail closed."""

    def __init__(self) -> None:
        self._policies: dict[str, Policy] = {}

    def register(self, name: str, policy: Policy | WritePolicy) -> None:
        if not name or not name.strip():
            raise ValueError("Policy names must be non-empty.")
        if isinstance(policy, WritePolicy):
            policy.assert_disabled()
        if name in self._policies:
            raise ValueError(f"Policy {name!r} is already registered.")
        if not policy.enabled:
            raise ValueError("Disabled policies cannot be registered.")
        self._policies[name] = policy

    def get(self, name: str) -> Policy:
        try:
            return self._policies[name]
        except KeyError:
            raise safe_error(ErrorCode.PERMISSION_DENIED) from None

    def contains(self, name: str) -> bool:
        return name in self._policies

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._policies))

    def items(self) -> tuple[tuple[str, Policy], ...]:
        return tuple((name, self._policies[name]) for name in self.names())

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self._policies)

    def as_mapping(self) -> Mapping[str, Policy]:
        return dict(self.items())

    def clear(self) -> None:
        self._policies.clear()


_default_registry = PolicyRegistry()


def get_registry() -> PolicyRegistry:
    return _default_registry


def reset_registry() -> None:
    """Drop all registered policies. Intended for tests only."""
    _default_registry.clear()
