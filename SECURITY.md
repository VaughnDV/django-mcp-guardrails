# Security policy

## Supported versions

This package is in alpha and has not published a stable release. Security fixes will land on `main` until versioned support is documented after the first release.

## Reporting a vulnerability

Do not open a public GitHub issue for security reports.

Please report vulnerabilities through [GitHub private vulnerability reporting](https://github.com/VaughnDV/django-mcp-guardrails/security/advisories/new).

Include:

- A description of the issue and its impact
- Reproduction steps or a proof of concept that does not include production data
- Affected versions or commit hashes when known

You should receive an acknowledgement within 7 days. We will coordinate a fix and disclosure timeline with you.

## Scope notes

`django-mcp-guardrails` enforces server-side policy for Django MCP tools. It does not:

- Replace Django authentication, permissions, or database access controls
- Detect every prompt injection
- Act as a general data-loss-prevention product
- Implement MCP transports or an OAuth server

Please still report issues that would let a client bypass allowlists, tenant scope, output sanitization, or export limits.

## Secrets and audit data

Never commit `.env` files, OAuth material, audit exports, database dumps, or credentials. Default audit behavior must not store prompts, results, access tokens, or secret-bearing URLs.
