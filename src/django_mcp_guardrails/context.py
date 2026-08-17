"""Trusted policy context. Identity never comes from tool arguments."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Authenticated caller identity derived from trusted server context.

    Milestone 2 adds construction from a Django request. Callers must never
    populate this object from model-generated tool arguments.
    """

    is_authenticated: bool
    user_id: str | int | None = None
    organization_id: str | int | None = None
    client_id: str | None = None
    correlation_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scopes", frozenset(self.scopes))
        if self.is_authenticated and self.user_id is None:
            raise ValueError("Authenticated context requires a user_id.")
        if not self.is_authenticated:
            object.__setattr__(self, "user_id", None)
            object.__setattr__(self, "organization_id", None)
            object.__setattr__(self, "client_id", None)
            object.__setattr__(self, "scopes", frozenset())

    @classmethod
    def anonymous(cls) -> PolicyContext:
        return cls(is_authenticated=False)

    @classmethod
    def authenticated(
        cls,
        user_id: str | int,
        *,
        organization_id: str | int | None = None,
        client_id: str | None = None,
        correlation_id: str | None = None,
        scopes: Iterable[str] = (),
    ) -> PolicyContext:
        return cls(
            is_authenticated=True,
            user_id=user_id,
            organization_id=organization_id,
            client_id=client_id,
            correlation_id=correlation_id,
            scopes=frozenset(scopes),
        )
