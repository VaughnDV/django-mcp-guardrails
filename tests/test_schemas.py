"""Schema generation and policy construction tests."""

from __future__ import annotations

import pytest

from django_mcp_guardrails import (
    ModelReadPolicy,
    generate_input_schema,
    generate_output_schema,
)
from django_mcp_guardrails.policies import ToolPolicy


def test_output_schema_lists_fields_in_sorted_order(
    read_policy: ModelReadPolicy,
) -> None:
    schema = generate_output_schema(read_policy)
    properties = schema["properties"]["items"]["items"]["properties"]
    assert list(properties) == ["id", "industry", "name"]
    assert schema["additionalProperties"] is False


def test_input_schema_does_not_advertise_unknown_fields(
    read_policy: ModelReadPolicy,
) -> None:
    schema = generate_input_schema(read_policy)
    assert schema["additionalProperties"] is False
    filter_properties = schema["properties"]["filters"]["oneOf"][0]["properties"]
    assert "password" not in filter_properties
    assert set(filter_properties) == {"industry", "name", "status"}


def test_tool_policy_schema_has_no_query_vocabulary() -> None:
    policy = ToolPolicy(return_fields={"ok"})
    schema = generate_input_schema(policy)
    assert schema["properties"] == {}


def test_invalid_limit_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        ModelReadPolicy(default_limit=50, max_limit=10)
    with pytest.raises(ValueError):
        ModelReadPolicy(default_limit=0)
