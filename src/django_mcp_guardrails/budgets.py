"""Per-call and cumulative export budgets keyed by trusted identity."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol, cast

from django_mcp_guardrails.context import PolicyContext
from django_mcp_guardrails.errors import ErrorCode, safe_error
from django_mcp_guardrails.policies import ModelReadPolicy, Policy
from django_mcp_guardrails.queries import NormalizedQuery, query_digest_shape


class BudgetBackend(Protocol):
    def add_rows(self, key: str, amount: int) -> int: ...

    def add_page(self, key: str, page: int) -> int: ...

    def reset(self) -> None: ...


class _Cache(Protocol):
    def add(self, key: str, value: object, timeout: int | None = None) -> bool: ...

    def incr(self, key: str, delta: int = 1) -> int: ...

    def set(self, key: str, value: object, timeout: int | None = None) -> None: ...

    def get(self, key: str, default: object = None) -> object: ...

    def clear(self) -> None: ...


class MemoryBudgetBackend:
    """In-process counters. Use Django cache for multi-process deployments."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, int] = defaultdict(int)
        self._pages: dict[str, set[int]] = defaultdict(set)

    def add_rows(self, key: str, amount: int) -> int:
        with self._lock:
            self._rows[key] += amount
            return self._rows[key]

    def add_page(self, key: str, page: int) -> int:
        with self._lock:
            self._pages[key].add(page)
            return len(self._pages[key])

    def reset(self) -> None:
        with self._lock:
            self._rows.clear()
            self._pages.clear()


class CacheBudgetBackend:
    """Django cache counters for multi-process enforcement of hourly windows."""

    def __init__(self, alias: str = "default", timeout: int = 7200) -> None:
        self._alias = alias
        self._timeout = timeout

    def add_rows(self, key: str, amount: int) -> int:
        cache = self._cache()
        cache_key = self._cache_key(key)
        cache.add(cache_key, 0, timeout=self._timeout)
        try:
            return int(cache.incr(cache_key, amount))
        except ValueError:
            cache.set(cache_key, amount, timeout=self._timeout)
            return amount

    def add_page(self, key: str, page: int) -> int:
        cache = self._cache()
        page_key = self._cache_key(f"{key}:p:{page}")
        count_key = self._cache_key(f"{key}:n")
        added = cache.add(page_key, 1, timeout=self._timeout)
        cache.add(count_key, 0, timeout=self._timeout)
        if added:
            try:
                return int(cache.incr(count_key))
            except ValueError:
                cache.set(count_key, 1, timeout=self._timeout)
                return 1
        current = cache.get(count_key)
        return current if isinstance(current, int) else 0

    def reset(self) -> None:
        self._cache().clear()

    def _cache(self) -> _Cache:
        from django.core.cache import caches

        return cast(_Cache, caches[self._alias])

    def _cache_key(self, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"django_mcp_guardrails:{digest}"


_backend: BudgetBackend = MemoryBudgetBackend()


def get_budget_backend() -> BudgetBackend:
    return _backend


def set_budget_backend(backend: BudgetBackend) -> None:
    global _backend
    _backend = backend


def reset_budgets() -> None:
    get_budget_backend().reset()


def enforce_budgets(
    policy: Policy,
    context: PolicyContext,
    query: NormalizedQuery,
    *,
    tool_name: str,
    row_count: int,
) -> None:
    """Apply cumulative row and distinct-page limits after a successful read."""
    if not isinstance(policy, ModelReadPolicy):
        return
    key = budget_key(context, tool_name, query)
    backend = get_budget_backend()
    if policy.max_pages is not None:
        distinct_pages = backend.add_page(f"{key}:pages", query.page)
        if distinct_pages > policy.max_pages:
            raise safe_error(ErrorCode.BULK_EXPORT_BLOCKED)
    if policy.max_session_rows is not None:
        total = backend.add_rows(f"{key}:rows", row_count)
        if total > policy.max_session_rows:
            raise safe_error(ErrorCode.SESSION_BUDGET_EXCEEDED)


def budget_key(context: PolicyContext, tool_name: str, query: NormalizedQuery) -> str:
    window = datetime.now(UTC).strftime("%Y-%m-%dT%H")
    digest = filter_digest(query)
    return "|".join(
        [
            str(context.user_id or ""),
            str(context.client_id or ""),
            tool_name,
            window,
            digest,
        ]
    )


def filter_digest(query: NormalizedQuery) -> str:
    shape = query_digest_shape(query)
    shape.pop("page", None)
    shape["filter_value_digests"] = [
        hashlib.sha256(repr(clause.value).encode("utf-8")).hexdigest()
        for clause in query.filters
    ]
    encoded = json.dumps(shape, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
