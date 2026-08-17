# Threat model

This document records residual risks. Server-side policy reduces exposure; it
does not make MCP access equivalent to a human using a least-privilege UI.

## Assets

- Tenant-scoped Django records
- Field-level confidential attributes
- Export volume (bulk reconstruction)
- Authentication and client identity
- Audit integrity

## Actors

- Authenticated MCP clients acting for a user
- Untrusted tool arguments and retrieved content (prompt injection)
- Other tools in the same agent session (confused deputy)
- Operators with log access

## Controls in this package

- Deny by default; missing policies fail closed
- Identity from trusted request context only
- Explicit query vocabulary and output allowlists
- Per-call row/byte limits and optional cumulative budgets
- Privacy-safe audit metadata
- django-mcp-server adapter that does not monkey-patch the framework

## Residual risks

### Prompt injection

Content stored in allowlisted fields can instruct an agent to call other tools.
This package does not inspect natural-language field values for injection.

### Confused deputy

An agent may combine this tool with others. Treat every tool result as
untrusted input to the next tool. Do not put secrets in tool descriptions.

### Tenant leakage

Scoped querysets are the application’s responsibility. A queryset factory that
omits organization filters will leak. System checks warn when `queryset` is
missing; they cannot prove the callback is correct.

### Repeated-query reconstruction

Row limits bound a single response. Clients can retry with new filters or
pages. `max_session_rows` and `max_pages` reduce this; they do not prevent all
reconstruction, especially across hours or clients.

### Aggregate inference

Approved aggregates are out of scope for 0.1. Do not add ad-hoc count/sum
tools without their own schemas and bounds.

### Output leakage

Allowlists can still include identifying fields. Nested objects without
`nested_return_fields` are emptied, but serialized strings may contain secrets
the application stored in an approved field.

### Framework compatibility

django-mcp-server 0.5.x requires MCP SDK 1.x. `ModelQueryToolset` and other
unwrapped framework features bypass this package. Version mismatches fail
closed in the adapter.

### Timing and existence

Empty results for another tenant’s identifiers are intentional, but timing
differences in the application queryset may still leak existence.

### Audit

Logging and database backends omit payloads by default. If you attach a custom
backend that stores request bodies, you accept that risk. Write-tool audits
fail closed when recording fails; read-tool audits fail open unless configured
otherwise.

## Acceptance mapping

| Criterion | Control |
| --- | --- |
| No query without a registered policy | Registry fail-closed |
| Disallowed filters rejected before QuerySet evaluation | `validate_query` |
| Extra application fields stripped | `sanitize_output` |
| Per-call limits not overridable | `limit_exceeded` / sanitizer clamp |
| Tenant scope from trusted request | `PolicyContext.from_request` |
| Inventory enumerates tools and risk | `mcp_guardrails_inventory` |
| Adversarial CI tests | `tests/test_adversarial.py` and adapter contracts |
| Integrates with an existing MCP framework | `django-mcp-guardrails[django-mcp-server]` |
