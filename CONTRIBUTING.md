# Contributing

Thanks for helping build a deny-by-default policy layer for Django MCP tools.

## Prerequisites

- Python 3.11+ (local default is pinned in `.python-version`)
- [Poetry](https://python-poetry.org/) 2.x
- [uv](https://docs.astral.sh/uv/)
- Git

## Local setup

```bash
git clone https://github.com/VaughnDV/django-mcp-guardrails.git
cd django-mcp-guardrails
uv venv --python 3.11
poetry install
cp .env.example .env
poetry run pre-commit install
```

Poetry is configured (`poetry.toml`) to reuse the in-project `.venv`. Do not commit `.venv` or `.env`.

Add runtime or development dependencies with Poetry, not by hand-editing lockfiles:

```bash
poetry add some-package
poetry add --group dev some-dev-package
```

## Checks

Run focused tests first, then the full quality gate:

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy
poetry build
poetry run twine check dist/*
```

Run these from the repository root. `pytest` is configured to measure only
`django_mcp_guardrails` (not `.venv` or site-packages) and to fail below 80%
coverage.

`pre-commit` runs Ruff, formatting, Poetry metadata checks, and secret/file hygiene on commit:

```bash
poetry run pre-commit run --all-files
```

Unit tests use `tests.settings`. They must not require secrets, network access, or a production database.

## Design rules

Read the published policy reference, adapter support matrix, and threat model before changing policy, adapters, query vocabulary, audit behavior, or public APIs.

- Keep the policy core framework-neutral.
- Adapters translate inputs and outputs; they do not redefine policy semantics.
- Do not copy employer-owned schemas, tools, or access rules from research references.
- Do not add infrastructure, persistence, or dependencies without a concrete requirement.

## Pull requests

- Keep changes small and complete.
- Add or update tests with behavior changes.
- Update the changelog under `## [Unreleased]`.
- Do not weaken deny-by-default rules to make a test pass.

## Releases

Do not publish from a coding agent unless a maintainer explicitly asks.

Ordinary CI on push and pull request never publishes. Production publishing is
[`.github/workflows/release.yml`](.github/workflows/release.yml), triggered
only by `release: types: [published]`. TestPyPI is a separately gated
`workflow_dispatch` workflow that requires a PEP 440 pre-release.

See [`docs/release.md`](docs/release.md) for Trusted Publishing, GitHub
environments, and the maintainer release checklist.
