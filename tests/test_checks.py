"""Django system check and management command tests."""

from __future__ import annotations

import json

import pytest
from django.core.management import CommandError, call_command
from django.test.utils import captured_stdout, override_settings

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
    assert payload[0]["max_limit"] == 50
    assert payload[0]["audit"] is True


def test_check_command_fails_on_high_severity() -> None:
    get_registry().register(
        "empty_tool",
        ModelReadPolicy(return_fields=set()),
    )
    with pytest.raises(Exception, match="high-severity"):
        call_command("mcp_guardrails_check")


def test_check_command_respects_baseline(tmp_path) -> None:
    get_registry().register(
        "empty_tool",
        ModelReadPolicy(return_fields=set()),
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "ignored": [
                    {"id": "django_mcp_guardrails.E002", "obj": "empty_tool"},
                ]
            }
        )
    )
    with captured_stdout() as stdout:
        call_command("mcp_guardrails_check", baseline=str(baseline))
    assert "No high-severity policy findings." in stdout.getvalue()
    assert "ignored" in stdout.getvalue()


def test_simulate_validates_without_running_the_queryset() -> None:
    def boom(_request: object) -> None:
        raise AssertionError("simulate must not evaluate a queryset")

    get_registry().register(
        "search_items",
        ModelReadPolicy(
            return_fields={"id", "name"},
            filter_fields={"name"},
            queryset=boom,
        ),
    )
    with captured_stdout() as stdout:
        call_command(
            "mcp_guardrails_simulate",
            "search_items",
            '{"filters": {"name": "secret-value"}}',
        )
    payload = json.loads(stdout.getvalue())
    assert payload["tool"] == "search_items"
    assert payload["query"]["filters"] == [{"field": "name", "lookup": "exact"}]
    assert "secret-value" not in stdout.getvalue()
    assert payload["page"] == 1


def test_simulate_unknown_tool_fails_closed() -> None:
    with pytest.raises(CommandError):
        call_command("mcp_guardrails_simulate", "missing_tool", "{}")


@override_settings(MCP_GUARDRAILS_AUDIT_STORE_PAYLOADS=True)
def test_payload_storing_audit_config_is_an_error() -> None:
    messages = check_policies()
    assert any(message.id == "django_mcp_guardrails.E006" for message in messages)
