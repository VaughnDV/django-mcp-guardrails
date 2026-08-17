"""JSON Schema generation for guarded tool results."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django_mcp_guardrails.outputs import ResultEnvelope
from django_mcp_guardrails.policies import ModelReadPolicy, ToolPolicy


def generate_output_schema(policy: ModelReadPolicy | ToolPolicy) -> dict[str, Any]:
    """Return a JSON Schema for the bounded result envelope."""
    item_properties = {
        name: _property_schema(name, policy) for name in sorted(policy.return_fields)
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["items", "meta"],
        "properties": {
            "items": {
                "type": "array",
                "maxItems": policy.max_limit,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": item_properties,
                },
            },
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "count",
                    "limit",
                    "has_more",
                    "truncated",
                    "policy_version",
                    "export_policy",
                ],
                "properties": {
                    "count": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1},
                    "has_more": {"type": "boolean"},
                    "truncated": {"type": "boolean"},
                    "policy_version": {"type": "string"},
                    "page": {"type": "integer", "minimum": 1},
                    "export_policy": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["bulk_export_supported", "max_rows_per_call"],
                        "properties": {
                            "bulk_export_supported": {"type": "boolean"},
                            "max_rows_per_call": {"type": "integer", "minimum": 1},
                            "max_session_rows": {"type": "integer", "minimum": 1},
                        },
                    },
                },
            },
        },
    }


def generate_input_schema(policy: ModelReadPolicy | ToolPolicy) -> dict[str, Any]:
    """Return a JSON Schema for the normalized query vocabulary."""
    if not isinstance(policy, ModelReadPolicy):
        return {"type": "object", "additionalProperties": False, "properties": {}}
    filter_names = sorted(policy.filter_fields)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "filters": {
                "oneOf": [
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": dict.fromkeys(filter_names, True),
                    },
                    {
                        "type": "array",
                        "maxItems": policy.max_filters,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["field", "value"],
                            "properties": {
                                "field": {"type": "string", "enum": filter_names},
                                "lookup": {"type": "string"},
                                "value": True,
                            },
                        },
                    },
                ]
            },
            "ordering": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Explicit ordering fields. Prefix with - for descending.",
            },
            "page": {"type": "integer", "minimum": 1},
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": policy.max_limit,
            },
            "search": {"type": "string", "maxLength": policy.max_string_length},
        },
    }


def envelope_matches_schema(
    envelope: ResultEnvelope, schema: Mapping[str, Any]
) -> bool:
    """Minimal validator for generated envelope schemas."""
    payload = envelope.to_dict()
    return _validate(payload, schema)


def _property_schema(name: str, policy: ModelReadPolicy | ToolPolicy) -> dict[str, Any]:
    nested = policy.nested_return_fields.get(name)
    if not nested:
        return {}
    properties = dict.fromkeys(sorted(nested), True)
    return {
        "oneOf": [
            {"type": "object", "additionalProperties": False, "properties": properties},
            {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": properties,
                },
            },
            {"type": "null"},
        ]
    }


def _validate(value: object, schema: Mapping[str, Any]) -> bool:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            return False
        required = schema.get("required", [])
        if any(key not in value for key in required):
            return False
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            if set(value) - allowed:
                return False
        properties = schema.get("properties", {})
        return all(
            _validate(child, properties[key])
            for key, child in value.items()
            if key in properties
            and isinstance(properties[key], Mapping)
            and properties[key]
            and properties[key] is not True
        )
    if schema_type == "array":
        if not isinstance(value, list):
            return False
        max_items = schema.get("maxItems")
        if max_items is not None and len(value) > max_items:
            return False
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            return all(_validate(item, item_schema) for item in value)
        return True
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if "oneOf" in schema:
        return any(
            option is True or (isinstance(option, Mapping) and _validate(value, option))
            for option in schema["oneOf"]
        )
    return True
