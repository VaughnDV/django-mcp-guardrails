"""Explicit read policy for the example catalog."""

from __future__ import annotations

from catalog.models import Item
from django_mcp_guardrails import ModelReadPolicy, PolicyContext, guarded_tool


def items_visible_to(request: object):
    organization_id = getattr(request, "organization_id", None)
    return Item.objects.filter(organization_id=organization_id)


item_read_policy = ModelReadPolicy(
    model=Item,
    queryset=items_visible_to,
    return_fields={"id", "name", "status"},
    filter_fields={"name", "status"},
    ordering_fields={"name", "id"},
    lookups={"name": {"exact", "icontains"}, "status": {"exact", "in"}},
    default_limit=25,
    max_limit=100,
    max_session_rows=500,
    max_pages=10,
)


@guarded_tool(policy=item_read_policy, risk="read")
def search_items(_context: PolicyContext, _query: object) -> list[dict[str, object]]:
    """Producer is unused because the policy supplies a scoped queryset."""
    return []
