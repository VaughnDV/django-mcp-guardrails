"""Explicit policy objects for guarded MCP tools and model surfaces."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NoReturn

from django_mcp_guardrails.errors import ErrorCode, GuardrailError

DEFAULT_POLICY_VERSION = "2026-08-01"
DEFAULT_LIMIT = 25
DEFAULT_MAX_LIMIT = 100
DEFAULT_MAX_IN_LIST = 50
DEFAULT_MAX_STRING_LENGTH = 256
DEFAULT_MAX_SERIALIZED_BYTES = 262_144
DEFAULT_MAX_FILTERS = 25
DEFAULT_MAX_RELATION_DEPTH = 1
DEFAULT_LOOKUPS: frozenset[str] = frozenset({"exact"})

SAFE_LOOKUPS: frozenset[str] = frozenset(
    {
        "exact",
        "iexact",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "contains",
        "icontains",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "isnull",
        "date",
        "year",
        "month",
        "day",
    }
)
UNSAFE_LOOKUPS: frozenset[str] = frozenset({"regex", "iregex", "search"})


class RiskLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


def _freeze_str_set(value: Iterable[str] | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    frozen = frozenset(value)
    for item in frozen:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Allowlist entries must be non-empty strings.")
    return frozen


def _freeze_lookups(
    lookups: Mapping[str, Iterable[str]] | None,
    *,
    allow_regex: bool,
) -> dict[str, frozenset[str]]:
    if not lookups:
        return {}
    frozen: dict[str, frozenset[str]] = {}
    for field_name, values in lookups.items():
        allowed = frozenset(values)
        unknown = allowed - SAFE_LOOKUPS - UNSAFE_LOOKUPS
        if unknown:
            raise ValueError("Unknown lookups are not permitted.")
        if allowed & UNSAFE_LOOKUPS and not allow_regex:
            raise ValueError("Regex and search lookups are disabled by default.")
        frozen[field_name] = allowed
    return frozen


def _require_relation_prefixes(
    paths: Iterable[str],
    relation_paths: frozenset[str],
    *,
    max_depth: int,
) -> None:
    for path in paths:
        depth = path.count(".")
        if depth > max_depth:
            raise ValueError("Relation depth exceeds the policy maximum.")
        if depth == 0:
            continue
        parts = path.split(".")
        for index in range(1, len(parts)):
            prefix = ".".join(parts[:index])
            if prefix not in relation_paths:
                raise ValueError("Dotted fields require an explicit relation path.")


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Policy for an arbitrary guarded callable."""

    risk: RiskLevel = RiskLevel.READ
    version: str = DEFAULT_POLICY_VERSION
    enabled: bool = True
    input_schema: Mapping[str, Any] | None = None
    output_schema: Mapping[str, Any] | None = None
    timeout_seconds: float | None = None
    rate_key: str | None = None
    audit: bool = True
    return_fields: frozenset[str] = field(default_factory=frozenset)
    nested_return_fields: Mapping[str, Iterable[str]] = field(default_factory=dict)
    max_limit: int = DEFAULT_MAX_LIMIT
    default_limit: int = DEFAULT_LIMIT
    max_serialized_bytes: int = DEFAULT_MAX_SERIALIZED_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", _coerce_risk(self.risk))
        object.__setattr__(self, "return_fields", _freeze_str_set(self.return_fields))
        nested = {
            key: _freeze_str_set(value)
            for key, value in dict(self.nested_return_fields).items()
        }
        object.__setattr__(self, "nested_return_fields", nested)
        if not self.version:
            raise ValueError("Policy version is required.")
        if self.default_limit < 1 or self.max_limit < 1:
            raise ValueError("Limits must be positive integers.")
        if self.max_limit < self.default_limit:
            raise ValueError(
                "max_limit must be greater than or equal to default_limit."
            )
        if self.max_serialized_bytes < 1:
            raise ValueError("max_serialized_bytes must be a positive integer.")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")


@dataclass(frozen=True, slots=True)
class ModelReadPolicy:
    """Deny-by-default read policy for a Django model surface."""

    model: type[Any] | str | None = None
    queryset: Callable[..., Any] | None = None
    return_fields: frozenset[str] = field(default_factory=frozenset)
    filter_fields: frozenset[str] = field(default_factory=frozenset)
    ordering_fields: frozenset[str] = field(default_factory=frozenset)
    relation_paths: frozenset[str] = field(default_factory=frozenset)
    nested_return_fields: Mapping[str, Iterable[str]] = field(default_factory=dict)
    lookups: Mapping[str, Iterable[str]] = field(default_factory=dict)
    default_limit: int = DEFAULT_LIMIT
    max_limit: int = DEFAULT_MAX_LIMIT
    max_session_rows: int | None = None
    max_in_list_length: int = DEFAULT_MAX_IN_LIST
    max_string_length: int = DEFAULT_MAX_STRING_LENGTH
    max_serialized_bytes: int = DEFAULT_MAX_SERIALIZED_BYTES
    max_filters: int = DEFAULT_MAX_FILTERS
    max_relation_depth: int = DEFAULT_MAX_RELATION_DEPTH
    max_pages: int | None = None
    allow_search: bool = False
    allow_regex: bool = False
    allow_skip_pagination: bool = False
    bulk_export_supported: bool = False
    risk: RiskLevel = RiskLevel.READ
    version: str = DEFAULT_POLICY_VERSION
    enabled: bool = True
    audit: bool = True
    object_permission: Callable[..., bool] | None = None
    search_handler: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", _coerce_risk(self.risk))
        object.__setattr__(self, "return_fields", _freeze_str_set(self.return_fields))
        object.__setattr__(self, "filter_fields", _freeze_str_set(self.filter_fields))
        object.__setattr__(
            self, "ordering_fields", _freeze_str_set(self.ordering_fields)
        )
        object.__setattr__(self, "relation_paths", _freeze_str_set(self.relation_paths))
        nested = {
            key: _freeze_str_set(value)
            for key, value in dict(self.nested_return_fields).items()
        }
        object.__setattr__(self, "nested_return_fields", nested)
        object.__setattr__(
            self,
            "lookups",
            _freeze_lookups(self.lookups, allow_regex=self.allow_regex),
        )
        if self.risk is not RiskLevel.READ:
            raise ValueError("ModelReadPolicy only supports read risk.")
        if not self.version:
            raise ValueError("Policy version is required.")
        if self.default_limit < 1 or self.max_limit < 1:
            raise ValueError("Limits must be positive integers.")
        if self.max_limit < self.default_limit:
            raise ValueError(
                "max_limit must be greater than or equal to default_limit."
            )
        if self.max_in_list_length < 1 or self.max_string_length < 1:
            raise ValueError("Operand bounds must be positive integers.")
        if self.max_serialized_bytes < 1:
            raise ValueError("max_serialized_bytes must be a positive integer.")
        if self.max_filters < 1:
            raise ValueError("max_filters must be a positive integer.")
        if self.max_relation_depth < 0:
            raise ValueError("max_relation_depth cannot be negative.")
        if self.max_session_rows is not None and self.max_session_rows < 1:
            raise ValueError("max_session_rows must be a positive integer.")
        if self.max_pages is not None and self.max_pages < 1:
            raise ValueError("max_pages must be a positive integer.")
        unknown_lookup_fields = set(self.lookups) - set(self.filter_fields)
        if unknown_lookup_fields:
            raise ValueError("Lookups must only be declared for filter_fields.")
        _require_relation_prefixes(
            self.filter_fields | self.ordering_fields | self.return_fields,
            self.relation_paths,
            max_depth=self.max_relation_depth,
        )
        unknown_nested = set(self.nested_return_fields) - set(self.return_fields)
        if unknown_nested:
            raise ValueError("Nested return fields must also appear in return_fields.")

    def lookups_for(self, field_name: str) -> frozenset[str]:
        declared = self.lookups.get(field_name)
        if declared is None:
            return DEFAULT_LOOKUPS
        return frozenset(declared)


@dataclass(frozen=True, slots=True)
class WritePolicy:
    """Experimental write policy. Execution is disabled by default."""

    enabled: bool = False
    risk: RiskLevel = RiskLevel.WRITE
    version: str = DEFAULT_POLICY_VERSION
    django_permission: str | None = None
    object_permission: Callable[..., bool] | None = None
    require_idempotency_key: bool = True
    allow_preview: bool = True
    confirmation_from_trusted_context: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", _coerce_risk(self.risk))
        if self.enabled:
            raise ValueError("Write policies are disabled in version 0.1.")

    def assert_disabled(self) -> NoReturn:
        raise GuardrailError(
            ErrorCode.PERMISSION_DENIED,
            "Write tools are disabled.",
        )


def _coerce_risk(value: RiskLevel | str) -> RiskLevel:
    try:
        return value if isinstance(value, RiskLevel) else RiskLevel(value)
    except ValueError as exc:
        raise ValueError("Unknown risk levels are not permitted.") from exc


Policy = ToolPolicy | ModelReadPolicy
