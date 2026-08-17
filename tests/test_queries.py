"""Query validation tests for the deny-by-default vocabulary."""

from __future__ import annotations

from datetime import date

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    validate_query,
)
from django_mcp_guardrails.queries import query_digest_shape


def test_exact_filters_and_defaults(read_policy: ModelReadPolicy) -> None:
    query = validate_query(
        read_policy,
        {"filters": {"name": "Acme"}, "ordering": ["name"]},
    )
    assert query.limit == 25
    assert query.page == 1
    assert query.filters[0].field == "name"
    assert query.filters[0].lookup == "exact"
    assert query.ordering == ("name",)


def test_empty_filter_allowlist_denies_filters() -> None:
    policy = ModelReadPolicy(return_fields={"id"}, filter_fields=set())
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(policy, {"filters": {"name": "Acme"}})
    assert exc_info.value.code is ErrorCode.FIELD_NOT_ALLOWED
    assert "name" not in exc_info.value.message


def test_unknown_filter_field_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"filters": {"password": "secret"}})
    assert exc_info.value.code is ErrorCode.FIELD_NOT_ALLOWED
    assert "password" not in exc_info.value.message
    assert "secret" not in exc_info.value.message


def test_django_lookup_suffix_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"filters": {"name__icontains": "acme"}})
    assert exc_info.value.code is ErrorCode.LOOKUP_NOT_ALLOWED
    assert "icontains" not in exc_info.value.message


def test_explicit_lookup_must_be_enabled(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(
            read_policy,
            {"filters": [{"field": "status", "lookup": "icontains", "value": "a"}]},
        )
    assert exc_info.value.code is ErrorCode.LOOKUP_NOT_ALLOWED


def test_enabled_in_lookup_is_bounded(read_policy: ModelReadPolicy) -> None:
    query = validate_query(
        read_policy,
        {
            "filters": [
                {"field": "status", "lookup": "in", "value": ["active", "pending"]}
            ]
        },
    )
    assert query.filters[0].value == ("active", "pending")


def test_huge_in_list_is_rejected(read_policy: ModelReadPolicy) -> None:
    values = [f"value-{index}" for index in range(read_policy.max_in_list_length + 1)]
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(
            read_policy,
            {"filters": [{"field": "status", "lookup": "in", "value": values}]},
        )
    assert exc_info.value.code is ErrorCode.INVALID_QUERY


def test_in_lookup_rejects_strings_as_sequences(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(
            read_policy,
            {"filters": [{"field": "status", "lookup": "in", "value": "active"}]},
        )
    assert exc_info.value.code is ErrorCode.INVALID_QUERY


def test_regex_is_rejected_by_default() -> None:
    with pytest.raises(ValueError, match="Regex"):
        ModelReadPolicy(
            filter_fields={"name"},
            lookups={"name": {"regex"}},
        )


def test_date_range_requires_enabled_lookup() -> None:
    policy = ModelReadPolicy(
        filter_fields={"created_on"},
        lookups={"created_on": {"gte", "lte"}},
    )
    query = validate_query(
        policy,
        {
            "filters": [
                {"field": "created_on", "lookup": "gte", "value": "2026-01-01"},
                {"field": "created_on", "lookup": "lte", "value": date(2026, 12, 31)},
            ]
        },
    )
    assert query.filters[0].value == date(2026, 1, 1)


def test_unapproved_relation_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"filters": {"owner.email": "a@example.com"}})
    assert exc_info.value.code is ErrorCode.FIELD_NOT_ALLOWED


def test_deep_relation_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="Relation depth"):
        ModelReadPolicy(
            filter_fields={"industry.group.name"},
            relation_paths={"industry", "industry.group"},
            max_relation_depth=1,
        )


def test_dotted_filter_requires_relation_path() -> None:
    policy = ModelReadPolicy(
        filter_fields={"industry.name"},
        relation_paths={"industry"},
        lookups={"industry.name": {"exact"}},
    )
    query = validate_query(policy, {"filters": {"industry.name": "Tech"}})
    assert query.filters[0].field == "industry.name"


def test_raw_sql_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"raw": "SELECT * FROM sponsor"})
    assert exc_info.value.code is ErrorCode.LOOKUP_NOT_ALLOWED


def test_sql_in_string_operand_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(
            read_policy,
            {"filters": {"name": "SELECT password FROM auth_user"}},
        )
    assert exc_info.value.code is ErrorCode.LOOKUP_NOT_ALLOWED


def test_pipeline_and_annotations_are_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"pipeline": [{"$match": {}}]})
    assert exc_info.value.code is ErrorCode.LOOKUP_NOT_ALLOWED
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"annotate": {"count": 1}})
    assert exc_info.value.code is ErrorCode.INVALID_QUERY


def test_skip_pagination_is_blocked(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"skip": 1000})
    assert exc_info.value.code is ErrorCode.BULK_EXPORT_BLOCKED


def test_negative_and_overflow_limits_are_rejected(
    read_policy: ModelReadPolicy,
) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"limit": 0})
    assert exc_info.value.code is ErrorCode.INVALID_QUERY
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"limit": -1})
    assert exc_info.value.code is ErrorCode.INVALID_QUERY
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"limit": 10_000})
    assert exc_info.value.code is ErrorCode.LIMIT_EXCEEDED
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"limit": 10**18})
    assert exc_info.value.code is ErrorCode.LIMIT_EXCEEDED


def test_identity_spoofing_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(
            read_policy,
            {
                "filters": {"name": "Acme"},
                "user_id": "admin",
                "organization_id": "other",
            },
        )
    assert exc_info.value.code is ErrorCode.PERMISSION_DENIED


def test_search_requires_opt_in(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"search": "acme"})
    assert exc_info.value.code is ErrorCode.LOOKUP_NOT_ALLOWED


def test_search_is_bounded_when_enabled() -> None:
    policy = ModelReadPolicy(
        filter_fields={"name"}, allow_search=True, max_string_length=8
    )
    with pytest.raises(GuardrailError):
        validate_query(policy, {"search": "abcdefghijk"})
    query = validate_query(policy, {"search": "acme"})
    assert query.search == "acme"


def test_ordering_must_be_allowlisted(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"ordering": ["secret"]})
    assert exc_info.value.code is ErrorCode.FIELD_NOT_ALLOWED
    query = validate_query(read_policy, {"ordering": ["-name"]})
    assert query.ordering == ("-name",)


def test_duplicate_ordering_is_rejected(read_policy: ModelReadPolicy) -> None:
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(read_policy, {"ordering": ["name", "name"]})
    assert exc_info.value.code is ErrorCode.INVALID_QUERY


def test_max_pages_blocks_deep_page_walk() -> None:
    policy = ModelReadPolicy(return_fields={"id"}, max_pages=3)
    with pytest.raises(GuardrailError) as exc_info:
        validate_query(policy, {"page": 4})
    assert exc_info.value.code is ErrorCode.BULK_EXPORT_BLOCKED


def test_query_digest_omits_values(read_policy: ModelReadPolicy) -> None:
    query = validate_query(read_policy, {"filters": {"name": "secret-value"}})
    shape = query_digest_shape(query)
    assert shape["filters"] == [{"field": "name", "lookup": "exact"}]
    assert "secret-value" not in str(shape)
