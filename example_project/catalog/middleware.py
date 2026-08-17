"""Middleware that attaches organization scope from the authenticated user."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class OrganizationContextMiddleware:
    """Trusted tenant scope. Never read organization from query parameters."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.organization_id = None  # type: ignore[attr-defined]
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            organization = user.organizations.order_by("id").first()
            if organization is not None:
                request.organization_id = organization.pk  # type: ignore[attr-defined]
        return self.get_response(request)
