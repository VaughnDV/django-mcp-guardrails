# django-mcp-guardrails

Deny-by-default policy and output protection for Django applications that already expose [Model Context Protocol](https://modelcontextprotocol.io/) tools.

This package does **not** implement another MCP transport or auto-publish Django models. It is a policy wrapper that sits between an existing MCP framework and Django QuerySets:

```text
MCP transport/framework
        ↓
django-mcp-guardrails policy wrapper
        ↓
Django permissions + scoped QuerySets
        ↓
sanitized, bounded, typed tool result
```

Status: **alpha**. Deny-by-default read policies, Django QuerySet integration,
the django-mcp-server adapter, cumulative export budgets, and privacy-safe
audit metadata are implemented. Publishing to PyPI still requires a dedicated
GitHub Release; see [docs/release.md](docs/release.md).

## Requirements

- Python 3.11+
- Django 5.2, 6.0, or 6.1

## Installation

```bash
pip install django-mcp-guardrails
```

Optional extras:

```bash
pip install "django-mcp-guardrails[django-mcp-server]"
pip install "django-mcp-guardrails[mcp-sdk]"
pip install "django-mcp-guardrails[audit]"
```

The `audit` extra currently adds no extra dependencies. The optional
`AuditEvent` model ships with the Django app; enable it with
`DatabaseAuditBackend` after migrating.

Add the app to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "django_mcp_guardrails",
]
```

## Guard a read tool

```python
from django_mcp_guardrails import ModelReadPolicy, PolicyContext, guarded_tool

policy = ModelReadPolicy(
    model="Sponsor",
    return_fields={"id", "name", "industry"},
    filter_fields={"name", "industry", "status"},
    ordering_fields={"name"},
    default_limit=25,
    max_limit=100,
    max_session_rows=500,
    max_pages=10,
)


@guarded_tool(policy=policy, risk="read")
def search_sponsors(context: PolicyContext, query):
    # Return already-serialized mappings. QuerySets are rejected.
    return [{"id": 1, "name": "Acme", "password": "stripped"}]


result = search_sponsors(
    PolicyContext.authenticated("user-1"),
    {"filters": {"name": "Acme"}, "limit": 10},
)
```

Missing policies fail closed. Empty allowlists grant nothing. Client-supplied
identity keys are ignored as untrusted and rejected. See
[docs/policy-reference.md](docs/policy-reference.md).

## Development

This repository uses [Poetry](https://python-poetry.org/) for dependencies and [uv](https://docs.astral.sh/uv/) to create the in-project `.venv`.

```bash
uv venv --python 3.11
poetry install
cp .env.example .env
poetry run pre-commit install
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow.

## Version 0.1 intent

Missing policies fail closed. Authentication and tenant scope come from the trusted Django request, never from tool arguments. Query validation happens before QuerySet evaluation. Serialized results cross a final output allowlist. Limits are enforced on the server. Auditing records decisions and sizes, not sensitive payloads.

Write tools stay disabled or experimental until the specification promotes them.

## Documentation

- [Policy reference](docs/policy-reference.md)
- [Adapter support matrix](docs/adapter-support.md)
- [Threat model](docs/threat-model.md)
- [Release publishing](docs/release.md)
- [Project specification](PROJECT_SPEC.md)
- [Contributor guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Docs index](docs/README.md)

## License

MIT. See [LICENSE](LICENSE).
