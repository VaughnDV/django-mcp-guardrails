# Documentation

The version 0.1 product contract lives in [`PROJECT_SPEC.md`](../PROJECT_SPEC.md). Treat that document as the source of truth for policy semantics, adapters, query vocabulary, audit behavior, and public APIs.

This directory will hold the policy reference, adapter support matrix, threat model, and stable error-code catalog as those features are implemented.

## Current status

- Framework-neutral read policy core, query validation, and output sanitization
  are implemented.
- Django QuerySet integration, MCP adapters, budgets, and audit logging are not
  implemented yet.

## Topics

| Document | Status |
| --- | --- |
| [Policy reference](policy-reference.md) | Milestone 1 |
| [Stable error codes](error-codes.md) | Milestone 1 |
| Adapter support matrix | Milestone 3 |
| Threat model and residual risks | Milestone 4 |
| Example application walkthrough | Milestone 2–3 |
