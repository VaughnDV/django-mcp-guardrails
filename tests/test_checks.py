"""Django system check and management command tests."""

from __future__ import annotations

import json

import pytest
from django.core.management import call_command
from django.test.utils import captured_stdout

from django_mcp_guardrails.checks import check_policies
from django_mcp_guardrails.policies import ModelReadPolicy
from django_mcp_guardrails.registry import get_registry


def test_empty_return_fields_is_an_error() -> None:
    get_registry().register(
        "empty_tool",
        ModelReadPolicy(return_fields=set(), filter_fields={"name"}),
    )
    messages = check_policies()
    assert any(message.id == "django_mcp_guardrails.E002" for message in messages)


def test_sensitive_return_fields_are_flagged() -> None:
    get_registry().register(
        "leaky_tool",
        ModelReadPolicy(return_fields={"id", "password"}),
    )
    messages = check_policies()
    assert any(message.id == "django_mcp_guardrails.E005" for message in messages)


def test_unbounded_limit_is_flagged() -> None:
    get_registry().register(
        "export_tool",
        ModelReadPolicy(return_fields={"id"}, max_limit=5000, default_limit=25),
    )
    messages = check_policies()
    assert any(message.id == "django_mcp_guardrails.E003" for message in messages)


def test_inventory_command_lists_registered_tools() -> None:
    get_registry().register(
        "search_items",
        ModelReadPolicy(return_fields={"id", "name"}, max_limit=50),
    )
    with captured_stdout() as stdout:
        call_command("mcp_guardrails_inventory", output_format="json")
    payload = json.loads(stdout.getvalue())
    assert payload[0]["name"] == "search_items"
    assert payload[0]["risk"] == "read"
    assert payload[0]["authentication"] == "trusted_request_context"


def test_check_command_fails_on_high_severity() -> None:
    get_registry().register(
        "empty_tool",
        ModelReadPolicy(return_fields=set()),
    )
    with pytest.raises(Exception, match="high-severity"):
        call_command("mcp_guardrails_check")
