# Stable error codes

Client-visible errors use these codes. Messages never include hidden field
names, model internals, SQL, or secret values.

| Code | When it is raised |
| --- | --- |
| `field_not_allowed` | Filter, ordering, or similar field is outside the allowlist. |
| `relation_not_allowed` | Relationship traversal is missing from `relation_paths` or too deep. |
| `lookup_not_allowed` | Lookup suffix, regex, raw SQL, or other unsafe operator. |
| `limit_exceeded` | Requested page size exceeds `max_limit`, or a single row cannot fit the byte budget. |
| `session_budget_exceeded` | Reserved for cumulative export budgets. |
| `bulk_export_blocked` | `skip`/`offset` pagination or page walk beyond `max_pages`. |
| `permission_denied` | Missing policy, disabled tool, identity spoofing, or write attempt. |
| `unauthenticated` | Policy evaluation without an authenticated trusted context. |
| `invalid_query` | Malformed types, bounds, or unknown query keys. |
| `output_schema_violation` | Non-mapping rows, QuerySets, unsafe values, or sanitized internal failures. |
