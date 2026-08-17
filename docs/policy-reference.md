# Policy reference

Status: implemented through Milestone 4 (read policies, Django QuerySets,
django-mcp-server adapter, cumulative budgets, and privacy-safe audit).

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
    max_session_rows=500,
    max_pages=10,
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
      "max_rows_per_call": 100,
      "max_session_rows": 500
    }
  }
}
```

Row and serialized-byte limits cannot be raised by client arguments.

## Budgets

Per-call `limit` / `max_limit` and `max_serialized_bytes` are enforced on the
actual sanitized result. Optional cumulative controls:

- `max_session_rows` — total rows returned for the same user, client, tool, and
  filter digest in an hourly window
- `max_pages` — maximum page number and distinct pages for that same key

Page walking uses a digest that **omits** `page`, so changing page does not
reset the row budget. Filter values are hashed into that digest and are not
stored. Keys come from trusted `PolicyContext` identity, never from tool
arguments.

The default backend is in-process memory. Multi-process deployments should
install a Django cache backend:

```python
from django_mcp_guardrails.budgets import CacheBudgetBackend, set_budget_backend

set_budget_backend(CacheBudgetBackend())
```

Hourly windows reset counters; they do not prevent reconstruction across hours
or clients. See [the threat model](threat-model.md).

## Audit

Successful and denied reads emit metadata: identities, policy version, filter
field names, a request digest, counts, serialized size, duration, truncation,
and decision. Prompts, results, and secret values are not recorded.

```python
from django_mcp_guardrails.audit import DatabaseAuditBackend, set_audit_backend

set_audit_backend(DatabaseAuditBackend())
```

Read-tool audit failures fail open unless `fail_closed=True`. Required write
audits fail closed. Do not set `MCP_GUARDRAILS_AUDIT_STORE_PAYLOADS`.

## Commands

- `mcp_guardrails_inventory` — list guarded tools, risk, fields, and limits
- `mcp_guardrails_check [--baseline baseline.json]` — fail CI on new errors
- `mcp_guardrails_simulate tool_name '{...}'` — validate a query without
  running the queryset

## Write policies

`WritePolicy` exists as an experimental type and cannot be enabled or
registered in this version.
