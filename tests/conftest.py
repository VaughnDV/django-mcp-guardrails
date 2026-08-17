"""Pytest configuration for django-mcp-guardrails."""

from __future__ import annotations

import pytest

from django_mcp_guardrails.policies import ModelReadPolicy
from django_mcp_guardrails.registry import reset_registry


@pytest.fixture(autouse=True)
def _reset_policy_registry() -> None:
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def read_policy() -> ModelReadPolicy:
    return ModelReadPolicy(
        model="Sponsor",
        return_fields={"id", "name", "industry"},
        filter_fields={"name", "industry", "status"},
        ordering_fields={"name", "date_added"},
        relation_paths={"industry"},
        nested_return_fields={"industry": {"id", "name"}},
        lookups={
            "name": {"exact", "icontains"},
            "industry": {"exact"},
            "status": {"exact", "in"},
        },
        default_limit=25,
        max_limit=100,
        max_session_rows=500,
    )
