"""Pytest configuration for django-mcp-guardrails."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.test import RequestFactory

from django_mcp_guardrails.policies import ModelReadPolicy
from django_mcp_guardrails.registry import reset_registry


@pytest.fixture(scope="session", autouse=True)
def _create_testapp_tables(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command("migrate", run_syncdb=True, verbosity=0)


@pytest.fixture(autouse=True)
def _reset_policy_registry() -> None:
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def factory() -> RequestFactory:
    return RequestFactory()


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
