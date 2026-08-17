"""Normalized query vocabulary validation for guarded reads."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from django_mcp_guardrails.errors import ErrorCode, safe_error
from django_mcp_guardrails.policies import UNSAFE_LOOKUPS, ModelReadPolicy, ToolPolicy

_FIELD_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_QUERY_KEYS = frozenset({"filters", "ordering", "page", "limit", "search"})
_IDENTITY_KEYS = frozenset(
    {
        "user",
        "user_id",
        "organization",
        "organization_id",
        "tenant",
        "tenant_id",
        "role",
        "is_admin",
        "scopes",
        "client_id",
        "authenticated",
        "request",
        "principal",
    }
)
_FORBIDDEN_QUERY_KEYS = frozenset(
    {
        "annotate",
        "annotations",
        "aggregate",
        "aggregation",
        "pipeline",
        "extra",
        "raw",
        "sql",
        "queryset",
        "serializer",
        "values",
        "defer",
        "only",
        "select_related",
        "prefetch_related",
        "skip",
        "offset",
        "regex",
        "search_vector",
    }
)


@dataclass(frozen=True, slots=True)
class FilterClause:
    field: str
    lookup: str
    value: object


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    filters: tuple[FilterClause, ...]
    ordering: tuple[str, ...]
    page: int
    limit: int
    search: str | None = None


def validate_query(
    policy: ModelReadPolicy | ToolPolicy,
    raw: Mapping[str, Any] | NormalizedQuery | None,
) -> NormalizedQuery:
    """Validate a client query against an explicit policy.

    Missing or empty filter allowlists grant no filters. Unknown keys, lookup
    suffixes, raw SQL, and identity spoofing are rejected before any database
    work would occur.
    """
    if isinstance(raw, NormalizedQuery):
        return validate_query(policy, _query_to_mapping(raw))
    payload = {} if raw is None else dict(raw)
    _reject_untrusted_keys(payload)
    if not isinstance(policy, ModelReadPolicy):
        return NormalizedQuery(
            filters=(), ordering=(), page=1, limit=policy.default_limit
        )
    return _validate_model_query(policy, payload)


def _query_to_mapping(query: NormalizedQuery) -> dict[str, Any]:
    return {
        "filters": [
            {"field": clause.field, "lookup": clause.lookup, "value": clause.value}
            for clause in query.filters
        ],
        "ordering": list(query.ordering),
        "page": query.page,
        "limit": query.limit,
        "search": query.search,
    }


def _reject_untrusted_keys(payload: Mapping[str, Any]) -> None:
    keys = set(payload)
    if keys & _IDENTITY_KEYS:
        raise safe_error(ErrorCode.PERMISSION_DENIED)
    if keys & _FORBIDDEN_QUERY_KEYS:
        if keys & {"skip", "offset"}:
            raise safe_error(ErrorCode.BULK_EXPORT_BLOCKED)
        if keys & {
            "regex",
            "pipeline",
            "raw",
            "sql",
            "extra",
            "aggregate",
            "aggregation",
        }:
            raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
        raise safe_error(ErrorCode.INVALID_QUERY)
    unknown = keys - _ALLOWED_QUERY_KEYS
    if unknown:
        raise safe_error(ErrorCode.INVALID_QUERY)


def _validate_model_query(
    policy: ModelReadPolicy, payload: Mapping[str, Any]
) -> NormalizedQuery:
    if not policy.enabled:
        raise safe_error(ErrorCode.PERMISSION_DENIED)
    filters = _parse_filters(policy, payload.get("filters"))
    ordering = _parse_ordering(policy, payload.get("ordering"))
    page = _parse_page(policy, payload.get("page", 1))
    limit = _parse_limit(policy, payload.get("limit"))
    search = _parse_search(policy, payload.get("search"))
    return NormalizedQuery(
        filters=filters,
        ordering=ordering,
        page=page,
        limit=limit,
        search=search,
    )


def _parse_filters(policy: ModelReadPolicy, raw: object) -> tuple[FilterClause, ...]:
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        clauses = [
            _parse_filter_clause(policy, field, "exact", value)
            for field, value in raw.items()
        ]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        clauses = [_parse_filter_item(policy, item) for item in raw]
    else:
        raise safe_error(ErrorCode.INVALID_QUERY)
    if len(clauses) > policy.max_filters:
        raise safe_error(ErrorCode.INVALID_QUERY)
    return tuple(clauses)


def _parse_filter_item(policy: ModelReadPolicy, item: object) -> FilterClause:
    if not isinstance(item, Mapping):
        raise safe_error(ErrorCode.INVALID_QUERY)
    allowed_keys = {"field", "lookup", "value"}
    if set(item) - allowed_keys:
        raise safe_error(ErrorCode.INVALID_QUERY)
    field = item.get("field")
    lookup = item.get("lookup", "exact")
    if "value" not in item:
        raise safe_error(ErrorCode.INVALID_QUERY)
    if not isinstance(field, str) or not isinstance(lookup, str):
        raise safe_error(ErrorCode.INVALID_QUERY)
    return _parse_filter_clause(policy, field, lookup, item.get("value"))


def _parse_filter_clause(
    policy: ModelReadPolicy,
    field: str,
    lookup: str,
    value: object,
) -> FilterClause:
    if "__" in field or not field:
        raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
    _assert_field_name(field)
    if field not in policy.filter_fields:
        raise safe_error(ErrorCode.FIELD_NOT_ALLOWED)
    _assert_relation_path(policy, field)
    if lookup in UNSAFE_LOOKUPS and not policy.allow_regex:
        raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
    if lookup not in policy.lookups_for(field):
        raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
    return FilterClause(
        field=field, lookup=lookup, value=_normalize_value(policy, lookup, value)
    )


def _normalize_value(policy: ModelReadPolicy, lookup: str, value: object) -> object:
    if lookup == "in":
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise safe_error(ErrorCode.INVALID_QUERY)
        if len(value) > policy.max_in_list_length:
            raise safe_error(ErrorCode.INVALID_QUERY)
        return tuple(_normalize_scalar(policy, item) for item in value)
    if lookup == "isnull":
        if not isinstance(value, bool):
            raise safe_error(ErrorCode.INVALID_QUERY)
        return value
    if lookup in {"gt", "gte", "lt", "lte", "date", "year", "month", "day"}:
        return _normalize_temporal_or_number(policy, lookup, value)
    return _normalize_scalar(policy, value)


def _normalize_scalar(policy: ModelReadPolicy, value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, bool) or not isinstance(value, int):
            return value
        if abs(value) > 10**18:
            raise safe_error(ErrorCode.INVALID_QUERY)
        return value
    if isinstance(value, str):
        if len(value) > policy.max_string_length:
            raise safe_error(ErrorCode.INVALID_QUERY)
        if _looks_like_sql(value):
            raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
        return value
    if isinstance(value, (date, datetime)):
        return value
    raise safe_error(ErrorCode.INVALID_QUERY)


def _normalize_temporal_or_number(
    policy: ModelReadPolicy, lookup: str, value: object
) -> object:
    if lookup in {"year", "month", "day"}:
        if not isinstance(value, int) or isinstance(value, bool):
            raise safe_error(ErrorCode.INVALID_QUERY)
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        if len(value) > policy.max_string_length:
            raise safe_error(ErrorCode.INVALID_QUERY)
        try:
            if "T" in value or " " in value:
                return datetime.fromisoformat(value)
            return date.fromisoformat(value)
        except ValueError as exc:
            raise safe_error(ErrorCode.INVALID_QUERY) from exc
    raise safe_error(ErrorCode.INVALID_QUERY)


def _parse_ordering(policy: ModelReadPolicy, raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise safe_error(ErrorCode.INVALID_QUERY)
    if not policy.ordering_fields and raw:
        raise safe_error(ErrorCode.FIELD_NOT_ALLOWED)
    seen: set[str] = set()
    ordering: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item or item in {",", ";", "--"}:
            raise safe_error(ErrorCode.INVALID_QUERY)
        descending = item.startswith("-")
        name = item[1:] if descending else item
        if "__" in name:
            raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
        _assert_field_name(name)
        if name not in policy.ordering_fields:
            raise safe_error(ErrorCode.FIELD_NOT_ALLOWED)
        _assert_relation_path(policy, name)
        if name in seen:
            raise safe_error(ErrorCode.INVALID_QUERY)
        seen.add(name)
        ordering.append(f"-{name}" if descending else name)
    return tuple(ordering)


def _parse_page(policy: ModelReadPolicy, raw: object) -> int:
    page = _parse_positive_int(raw)
    if policy.max_pages is not None and page > policy.max_pages:
        raise safe_error(ErrorCode.BULK_EXPORT_BLOCKED)
    return page


def _parse_limit(policy: ModelReadPolicy, raw: object) -> int:
    if raw is None:
        return policy.default_limit
    limit = _parse_positive_int(raw)
    if limit > policy.max_limit:
        raise safe_error(ErrorCode.LIMIT_EXCEEDED)
    return limit


def _parse_search(policy: ModelReadPolicy, raw: object) -> str | None:
    if raw is None:
        return None
    if not policy.allow_search:
        raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
    if not isinstance(raw, str):
        raise safe_error(ErrorCode.INVALID_QUERY)
    if len(raw) > policy.max_string_length:
        raise safe_error(ErrorCode.INVALID_QUERY)
    if _looks_like_sql(raw):
        raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
    return raw


def _parse_positive_int(raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise safe_error(ErrorCode.INVALID_QUERY)
    if raw < 1:
        raise safe_error(ErrorCode.INVALID_QUERY)
    if raw > 10**9:
        raise safe_error(ErrorCode.LIMIT_EXCEEDED)
    return raw


def _assert_field_name(field: str) -> None:
    for segment in field.split("."):
        if not _FIELD_SEGMENT_RE.match(segment):
            raise safe_error(ErrorCode.INVALID_QUERY)


def _assert_relation_path(policy: ModelReadPolicy, field: str) -> None:
    depth = field.count(".")
    if depth > policy.max_relation_depth:
        raise safe_error(ErrorCode.RELATION_NOT_ALLOWED)
    if depth == 0:
        return
    parts = field.split(".")
    for index in range(1, len(parts)):
        prefix = ".".join(parts[:index])
        if prefix not in policy.relation_paths:
            raise safe_error(ErrorCode.RELATION_NOT_ALLOWED)


def _looks_like_sql(value: str) -> bool:
    compact = " ".join(value.lower().split())
    keywords = ("select ", "insert ", "update ", "delete ", "drop ", "union ")
    padded = f" {compact}"
    if any(
        padded.startswith(f" {keyword}") or f" {keyword}" in padded
        for keyword in keywords
    ):
        return True
    return any(
        token in compact for token in ("--;", "/*", "pg_sleep", "information_schema")
    )


def query_digest_shape(query: NormalizedQuery) -> dict[str, object]:
    """Return a redacted, stable shape suitable for later audit records."""
    return {
        "filters": [
            {"field": clause.field, "lookup": clause.lookup} for clause in query.filters
        ],
        "ordering": list(query.ordering),
        "page": query.page,
        "limit": query.limit,
        "search": query.search is not None,
    }
