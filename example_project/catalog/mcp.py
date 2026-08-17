"""Optional django-mcp-server registration for the example project."""

from __future__ import annotations

from contextlib import suppress

from catalog.policies import item_read_policy
from django_mcp_guardrails.adapters.django_mcp_server import (
    AdapterUnavailable,
    register_guarded_model_tool,
)

with suppress(AdapterUnavailable):
    register_guarded_model_tool(
        policy=item_read_policy,
        name="search_items",
        get_organization_id=lambda request: getattr(request, "organization_id", None),
    )
