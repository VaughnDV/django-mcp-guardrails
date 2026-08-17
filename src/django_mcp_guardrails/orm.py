"""Translate approved query clauses into Django ORM expressions."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from django.db.models import QuerySet

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.errors import ErrorCode, safe_error
from django_mcp_guardrails.policies import ModelReadPolicy
from django_mcp_guardrails.queries import FilterClause, NormalizedQuery

_ORM_LOOKUPS: dict[str, str] = {
    "exact": "exact",
    "iexact": "iexact",
    "in": "in",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    "contains": "contains",
    "icontains": "icontains",
    "startswith": "startswith",
    "istartswith": "istartswith",
    "endswith": "endswith",
    "iendswith": "iendswith",
    "isnull": "isnull",
    "date": "date",
    "year": "year",
    "month": "month",
    "day": "day",
}


def fetch_serialized_rows(
    policy: ModelReadPolicy,
    context: PolicyContext,
    query: NormalizedQuery,
) -> list[dict[str, Any]]:
    """Scope, filter, bound, evaluate once, then serialize allowlisted fields."""
    queryset = resolve_queryset(policy, context)
    queryset = apply_normalized_query(queryset, query, policy)
    queryset = _optimize_relations(queryset, policy)
    queryset = queryset[: query.limit + 1]
    rows = list(queryset)
    if policy.object_permission is not None:
        rows = [row for row in rows if policy.object_permission(context, row)]
    return [serialize_instance(row, policy) for row in rows]


def resolve_queryset(policy: ModelReadPolicy, context: PolicyContext) -> QuerySet[Any]:
    if policy.queryset is None:
        raise safe_error(ErrorCode.PERMISSION_DENIED)
    queryset = _call_queryset(policy.queryset, context)
    if not isinstance(queryset, QuerySet):
        raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)
    return queryset


def apply_normalized_query(
    queryset: QuerySet[Any],
    query: NormalizedQuery,
    policy: ModelReadPolicy,
) -> QuerySet[Any]:
    """Apply validated filters and ordering. Tenant scope must already be in queryset."""
    for clause in query.filters:
        queryset = queryset.filter(**_clause_to_orm(clause))
    if query.search is not None:
        if policy.search_handler is None:
            raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
        queryset = policy.search_handler(queryset, query.search)
    if query.ordering:
        queryset = queryset.order_by(*(_order_to_orm(item) for item in query.ordering))
    return queryset


def serialize_instance(instance: object, policy: ModelReadPolicy) -> dict[str, Any]:
    """Read only allowlisted attributes. Never use model repr or meta internals."""
    payload: dict[str, Any] = {}
    for name in sorted(policy.return_fields):
        if not hasattr(instance, name.split(".", maxsplit=1)[0]):
            continue
        value = _resolve_attr(instance, name)
        nested = policy.nested_return_fields.get(name)
        if nested:
            payload[name] = _serialize_related(value, frozenset(nested))
        else:
            payload[name] = _serialize_scalar(value)
    return payload


def _call_queryset(factory: object, context: PolicyContext) -> object:
    try:
        signature = inspect.signature(factory)  # type: ignore[arg-type]
        parameters = list(signature.parameters)
    except (TypeError, ValueError):
        parameters = []
    if parameters and parameters[0] in {"request", "req"}:
        if context.request is None:
            raise safe_error(ErrorCode.PERMISSION_DENIED)
        return factory(context.request)  # type: ignore[operator]
    return factory(context)  # type: ignore[operator]


def _clause_to_orm(clause: FilterClause) -> dict[str, object]:
    lookup = _ORM_LOOKUPS.get(clause.lookup)
    if lookup is None:
        raise safe_error(ErrorCode.LOOKUP_NOT_ALLOWED)
    field_path = clause.field.replace(".", "__")
    return {f"{field_path}__{lookup}": clause.value}


def _order_to_orm(item: str) -> str:
    descending = item.startswith("-")
    name = item[1:] if descending else item
    path = name.replace(".", "__")
    return f"-{path}" if descending else path


def _optimize_relations(
    queryset: QuerySet[Any], policy: ModelReadPolicy
) -> QuerySet[Any]:
    related = tuple(
        path.replace(".", "__")
        for path in sorted(policy.relation_paths)
        if path in policy.return_fields
    )
    if related:
        return queryset.select_related(*related)
    return queryset


def _resolve_attr(instance: object, path: str) -> object:
    current: object = instance
    for segment in path.split("."):
        if current is None:
            return None
        current = getattr(current, segment, None)
    return current


def _serialize_related(value: object, allowed: frozenset[str]) -> object:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {key: value.get(key) for key in sorted(allowed) if key in value}
    payload: dict[str, Any] = {}
    for key in sorted(allowed):
        payload[key] = _serialize_scalar(getattr(value, key, None))
    return payload


def _serialize_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "isoformat"):
        isoformat = value.isoformat
        if callable(isoformat):
            return isoformat()
    return str(value)
