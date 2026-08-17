# Policy reference

Status: implemented through Django QuerySet integration (Milestone 2). MCP
adapters, cumulative budgets, and audit persistence are not implemented here.

## Deny by default

- A tool is not guarded until its policy is registered by name.
- Missing policies fail closed with `permission_denied`.
- Empty `return_fields` or `filter_fields` grant nothing, not everything.
- Unknown query keys, lookups, relations, risk levels, and policy versions are
  rejected.

## `ModelReadPolicy`

Declare an explicit allowlist for a read-only model surface. Provide a
queryset factory that applies tenant scope **before** client filters.

```python
from django_mcp_guardrails import (
    ModelReadPolicy,
    PolicyContext,
    execute_model_read,
    guarded_tool,
)

policy = ModelReadPolicy(
    model=Item,
    queryset=lambda request: Item.objects.filter(
        organization_id=request.organization_id
    ),
    return_fields={"id", "name", "industry"},
    filter_fields={"name", "industry", "status"},
    ordering_fields={"name", "date_added"},
    relation_paths={"industry"},
    nested_return_fields={"industry": {"id", "name"}},
    lookups={"name": {"exact", "icontains"}, "status": {"exact", "in"}},
    default_limit=25,
    max_limit=100,
)


@guarded_tool(policy=policy, risk="read")
def search_items(context: PolicyContext, query):
    return []  # unused when queryset is set


context = PolicyContext.from_request(
    request,
    get_organization_id=lambda req: getattr(req, "organization_id", None),
)
result = execute_model_read(policy, context, {"filters": {"name": "Acme"}})
```

`PolicyContext` must be built from trusted server state. Tool arguments that
include `user`, `organization`, `tenant`, `role`, or similar identity keys are
rejected.

## Query vocabulary

Accepted keys: `filters`, `ordering`, `page`, `limit`, `search`.

- `filters` may be a mapping of field → exact value, or a list of
  `{field, lookup, value}` objects.
- Lookups are never encoded in field names. `name__icontains` is rejected.
- `in` lists, strings, and page/limit values are bounded.
- `search` is off unless `allow_search=True`.
- `regex` / `iregex` are off unless `allow_regex=True` at policy construction.
- `skip`, `offset`, raw SQL, annotations, aggregations, and pipelines are
  rejected.

## Output envelope

Guarded producers must return a sequence of already-serialized mappings.
QuerySets and model instances are rejected. Extra keys are stripped. Nested
objects require `nested_return_fields`. Common secret field names are removed
even if allowlisted.

```json
{
  "items": [],
  "meta": {
    "count": 0,
    "limit": 25,
    "page": 1,
    "has_more": false,
    "truncated": false,
    "policy_version": "2026-08-01",
    "export_policy": {
      "bulk_export_supported": false,
      "max_rows_per_call": 100
    }
  }
}
```

Row and serialized-byte limits cannot be raised by client arguments.
Cumulative session budgets are declared on the policy (`max_session_rows`)
but not yet enforced across calls.

## Write policies

`WritePolicy` exists as an experimental type and cannot be enabled or
registered in this version.
