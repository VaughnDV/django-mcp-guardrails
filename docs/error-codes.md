# Stable error codes

Client-visible errors use these codes. Messages never include hidden field
names, model internals, SQL, or secret values.

| Code | When it is raised |
| --- | --- |
| `field_not_allowed` | Filter, ordering, or similar field is outside the allowlist. |
| `relation_not_allowed` | Relationship traversal is missing from `relation_paths` or too deep. |
| `lookup_not_allowed` | Lookup suffix, regex, raw SQL, or other unsafe operator. |
| `limit_exceeded` | Requested page size exceeds `max_limit`, or a single row cannot fit the byte budget. |
| `session_budget_exceeded` | Cumulative `max_session_rows` for the trusted identity and filter digest was exceeded. |
| `bulk_export_blocked` | `skip`/`offset` pagination, or a page number / distinct-page walk beyond `max_pages`. |
| `permission_denied` | Missing policy, disabled tool, identity spoofing, write attempt, or required audit failure. |
| `unauthenticated` | Policy evaluation without an authenticated trusted context. |
| `invalid_query` | Malformed types, bounds, or unknown query keys. |
| `output_schema_violation` | Non-mapping rows, QuerySets, unsafe values, or sanitized internal failures. |
