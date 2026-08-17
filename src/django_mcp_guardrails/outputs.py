"""Final output allowlisting, truncation metadata, and result envelopes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from django_mcp_guardrails.errors import ErrorCode, GuardrailError, safe_error
from django_mcp_guardrails.policies import ModelReadPolicy, ToolPolicy
from django_mcp_guardrails.queries import NormalizedQuery

_SECRET_FIELD_NAMES = frozenset(
    {
        "password",
        "passwd",
        "hashed_password",
        "password_hash",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "private_key",
        "authorization",
        "csrf",
        "session_id",
    }
)


@dataclass(frozen=True, slots=True)
class ExportPolicyMeta:
    bulk_export_supported: bool
    max_rows_per_call: int
    max_session_rows: int | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "bulk_export_supported": self.bulk_export_supported,
            "max_rows_per_call": self.max_rows_per_call,
        }
        if self.max_session_rows is not None:
            payload["max_session_rows"] = self.max_session_rows
        return payload


@dataclass(frozen=True, slots=True)
class ResultMeta:
    count: int
    limit: int
    has_more: bool
    truncated: bool
    policy_version: str
    export_policy: ExportPolicyMeta
    page: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "count": self.count,
            "limit": self.limit,
            "has_more": self.has_more,
            "truncated": self.truncated,
            "policy_version": self.policy_version,
            "export_policy": self.export_policy.to_dict(),
            "page": self.page,
        }


@dataclass(frozen=True, slots=True)
class ResultEnvelope:
    items: tuple[dict[str, Any], ...]
    meta: ResultMeta

    def to_dict(self) -> dict[str, Any]:
        return {"items": list(self.items), "meta": self.meta.to_dict()}


def sanitize_output(
    policy: ModelReadPolicy | ToolPolicy,
    items: object,
    *,
    query: NormalizedQuery | None = None,
) -> ResultEnvelope:
    """Retain only allowlisted fields and bound the serialized result."""
    _reject_queryset(items)
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes, Mapping)):
        raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)
    limit = query.limit if query is not None else policy.default_limit
    page = query.page if query is not None else 1
    has_more = len(items) > limit
    page_items = list(items[:limit])
    allowlist = _output_allowlist(policy)
    sanitized: list[dict[str, Any]] = [
        _sanitize_mapping(item, allowlist) for item in page_items
    ]
    truncated = has_more
    sanitized, byte_truncated = _clamp_serialized_bytes(
        sanitized, policy.max_serialized_bytes
    )
    truncated = truncated or byte_truncated
    export_policy = ExportPolicyMeta(
        bulk_export_supported=getattr(policy, "bulk_export_supported", False),
        max_rows_per_call=policy.max_limit,
        max_session_rows=getattr(policy, "max_session_rows", None),
    )
    return ResultEnvelope(
        items=tuple(sanitized),
        meta=ResultMeta(
            count=len(sanitized),
            limit=limit,
            has_more=has_more or byte_truncated,
            truncated=truncated,
            policy_version=policy.version,
            export_policy=export_policy,
            page=page,
        ),
    )


def _output_allowlist(policy: ModelReadPolicy | ToolPolicy) -> dict[str, Any]:
    nested = {
        key: {child: True for child in sorted(values)}
        for key, values in policy.nested_return_fields.items()
    }
    allowlist: dict[str, Any] = {}
    for name in sorted(policy.return_fields):
        allowlist[name] = nested.get(name, True)
    return allowlist


def _sanitize_mapping(item: object, allowlist: Mapping[str, Any]) -> dict[str, Any]:
    _reject_queryset(item)
    if not isinstance(item, Mapping):
        raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)
    if _looks_like_model(item):
        raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)
    result: dict[str, Any] = {}
    for key in allowlist:
        if key not in item or _is_private_field(key):
            continue
        spec = allowlist[key]
        value = item[key]
        _reject_queryset(value)
        if spec is True:
            result[key] = _sanitize_allowed_value(value)
        elif isinstance(spec, Mapping):
            result[key] = _sanitize_nested(value, spec)
    return result


def _sanitize_nested(value: object, spec: Mapping[str, Any]) -> object:
    if value is None:
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, Mapping)):
        return [_sanitize_mapping(item, spec) for item in value]
    if isinstance(value, Mapping):
        return _sanitize_mapping(value, spec)
    raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)


def _sanitize_allowed_value(value: object) -> object:
    _reject_queryset(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Mapping):
        # Nested mappings require an explicit nested schema.
        return {}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_sanitize_allowed_value(item) for item in value]
    raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION)


def _is_private_field(name: str) -> bool:
    lowered = name.lower()
    return name.startswith("_") or lowered in _SECRET_FIELD_NAMES


def _looks_like_model(item: object) -> bool:
    return hasattr(item, "_meta") and hasattr(item, "serializable_value")


def _reject_queryset(value: object) -> None:
    if _is_queryset(value):
        raise GuardrailError(
            ErrorCode.OUTPUT_SCHEMA_VIOLATION,
            "QuerySets cannot be returned from guarded tools.",
        )


def _is_queryset(value: object) -> bool:
    if hasattr(value, "_fetch_all") and hasattr(value, "_result_cache"):
        return True
    try:
        from django.db.models.query import QuerySet

        return isinstance(value, QuerySet)
    except Exception:  # pragma: no cover - Django always present in this package
        return False


def _clamp_serialized_bytes(
    items: list[dict[str, Any]], max_bytes: int
) -> tuple[list[dict[str, Any]], bool]:
    payload = _dump_bytes(items)
    if len(payload) <= max_bytes:
        return items, False
    clamped = list(items)
    while clamped and len(_dump_bytes(clamped)) > max_bytes:
        clamped.pop()
    if not clamped and items:
        raise safe_error(ErrorCode.LIMIT_EXCEEDED)
    return clamped, True


def _dump_bytes(items: Iterable[Mapping[str, Any]]) -> bytes:
    try:
        return json.dumps(
            list(items),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=_json_default,
        ).encode("utf-8")
    except TypeError as exc:
        raise safe_error(ErrorCode.OUTPUT_SCHEMA_VIOLATION) from exc


def _json_default(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError("value is not JSON serializable")
