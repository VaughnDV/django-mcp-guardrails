"""Trusted policy context. Identity never comes from tool arguments."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Authenticated caller identity derived from trusted server context.

    Callers must never populate this object from model-generated tool arguments.
    """

    is_authenticated: bool
    user_id: str | int | None = None
    organization_id: str | int | None = None
    client_id: str | None = None
    correlation_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    request: object | None = None

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
    def anonymous(cls, request: object | None = None) -> PolicyContext:
        return cls(is_authenticated=False, request=request)

    @classmethod
    def authenticated(
        cls,
        user_id: str | int,
        *,
        organization_id: str | int | None = None,
        client_id: str | None = None,
        correlation_id: str | None = None,
        scopes: Iterable[str] = (),
        request: object | None = None,
    ) -> PolicyContext:
        return cls(
            is_authenticated=True,
            user_id=user_id,
            organization_id=organization_id,
            client_id=client_id,
            correlation_id=correlation_id,
            scopes=frozenset(scopes),
            request=request,
        )

    @classmethod
    def from_request(
        cls,
        request: object,
        *,
        organization_id: str | int | None = None,
        client_id: str | None = None,
        correlation_id: str | None = None,
        scopes: Iterable[str] = (),
        get_organization_id: Callable[[object], Any] | None = None,
        get_client_id: Callable[[object], str | None] | None = None,
        get_scopes: Callable[[object], Iterable[str]] | None = None,
        get_correlation_id: Callable[[object], str | None] | None = None,
    ) -> PolicyContext:
        """Build context from an authenticated Django request.

        Organization, client, and scope values must come from trusted resolvers
        or server-side request attributes—not from query parameters or tool
        arguments.
        """
        user = getattr(request, "user", None)
        is_authenticated = bool(getattr(user, "is_authenticated", False))
        is_active = bool(getattr(user, "is_active", False))
        if not is_authenticated or not is_active or user is None:
            return cls.anonymous(request=request)
        user_id = getattr(user, "pk", None)
        if user_id is None:
            return cls.anonymous(request=request)
        resolved_org = (
            get_organization_id(request)
            if get_organization_id is not None
            else organization_id
        )
        resolved_client = (
            get_client_id(request) if get_client_id is not None else client_id
        )
        resolved_scopes = get_scopes(request) if get_scopes is not None else scopes
        resolved_correlation = (
            get_correlation_id(request)
            if get_correlation_id is not None
            else correlation_id
        )
        return cls.authenticated(
            user_id,
            organization_id=resolved_org,
            client_id=resolved_client,
            correlation_id=resolved_correlation,
            scopes=resolved_scopes,
            request=request,
        )
