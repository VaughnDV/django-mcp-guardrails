# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Package metadata versions describe planned work. They are not proof that a
release has been published.

## [Unreleased]

### Added

- Installable `django-mcp-guardrails` package scaffold with a Django `AppConfig`.
- Poetry 2 packaging, an in-project virtual environment, pytest, Ruff, mypy, and pre-commit.
- Optional extras for `django-mcp-server`, the official MCP Python SDK, and audit support.
- GitHub Actions CI for lint, type checking, tests across supported Python/Django versions, and package builds.
