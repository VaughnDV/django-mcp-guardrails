"""Output allowlisting, envelopes, and truncation tests."""

from __future__ import annotations

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    sanitize_output,
    validate_query,
)
from django_mcp_guardrails.queries import NormalizedQuery
from django_mcp_guardrails.schemas import (
    envelope_matches_schema,
    generate_output_schema,
)


def test_extra_application_fields_are_stripped(read_policy: ModelReadPolicy) -> None:
    envelope = sanitize_output(
        read_policy,
        [
            {
                "id": 1,
                "name": "Acme",
                "industry": {"id": 9, "name": "Tech", "internal_code": "nope"},
                "password": "hunter2",
                "_state": "hidden",
                "secret": "leak",
            }
        ],
    )
    item = envelope.items[0]
    assert item == {"id": 1, "industry": {"id": 9, "name": "Tech"}, "name": "Acme"}
    assert "password" not in item
    assert "secret" not in item
    assert envelope.meta.truncated is False
    assert envelope.meta.export_policy.max_rows_per_call == 100


def test_empty_return_allowlist_strips_all_fields() -> None:
    policy = ModelReadPolicy(filter_fields={"name"}, return_fields=set())
    envelope = sanitize_output(policy, [{"id": 1, "name": "Acme"}])
    assert envelope.items == ({},)


def test_nested_mapping_without_schema_is_not_expanded() -> None:
    policy = ModelReadPolicy(return_fields={"id", "owner"})
    envelope = sanitize_output(
        policy,
        [{"id": 1, "owner": {"id": 2, "email": "hidden@example.com"}}],
    )
    assert envelope.items[0]["owner"] == {}


def test_row_limit_clamps_and_sets_has_more(read_policy: ModelReadPolicy) -> None:
    query = validate_query(read_policy, {"limit": 2})
    envelope = sanitize_output(
        read_policy,
        [{"id": index, "name": str(index)} for index in range(5)],
        query=query,
    )
    assert [item["id"] for item in envelope.items] == [0, 1]
    assert envelope.meta.has_more is True
    assert envelope.meta.truncated is True
    assert envelope.meta.count == 2
    assert envelope.meta.limit == 2


def test_byte_limit_truncates_items() -> None:
    policy = ModelReadPolicy(
        return_fields={"name"},
        max_serialized_bytes=40,
        default_limit=10,
        max_limit=10,
    )
    envelope = sanitize_output(
        policy,
        [{"name": "abcdefghij"} for _ in range(5)],
    )
    assert envelope.meta.truncated is True
    assert envelope.meta.has_more is True
    assert len(envelope.items) < 5


def test_queryset_like_results_are_rejected(read_policy: ModelReadPolicy) -> None:
    class FakeQuerySet:
        _result_cache = None

        def _fetch_all(self) -> None:
            raise AssertionError("QuerySet must not be evaluated")

        def __len__(self) -> int:
            raise AssertionError("QuerySet must not be evaluated")

    with pytest.raises(GuardrailError) as exc_info:
        sanitize_output(read_policy, FakeQuerySet())
    assert exc_info.value.code is ErrorCode.OUTPUT_SCHEMA_VIOLATION
    assert "FakeQuerySet" not in exc_info.value.message


def test_non_mapping_rows_are_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        sanitize_output(read_policy, ["not-a-mapping"])
    assert exc_info.value.code is ErrorCode.OUTPUT_SCHEMA_VIOLATION


def test_envelope_is_json_serializable_and_matches_schema(
    read_policy: ModelReadPolicy,
) -> None:
    query = NormalizedQuery(filters=(), ordering=(), page=1, limit=25)
    envelope = sanitize_output(
        read_policy,
        [{"id": 1, "name": "Acme", "industry": {"id": 2, "name": "Tech"}}],
        query=query,
    )
    payload = envelope.to_dict()
    assert set(payload) == {"items", "meta"}
    schema = generate_output_schema(read_policy)
    assert envelope_matches_schema(envelope, schema)
    assert schema["properties"]["items"]["maxItems"] == 100


def test_output_key_order_is_deterministic(read_policy: ModelReadPolicy) -> None:
    envelope = sanitize_output(
        read_policy,
        [{"name": "Acme", "id": 1, "industry": {"name": "Tech", "id": 2}}],
    )
    assert list(envelope.items[0]) == ["id", "industry", "name"]
    assert list(envelope.items[0]["industry"]) == ["id", "name"]
