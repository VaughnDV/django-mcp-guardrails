"""Cumulative export budget tests."""

from __future__ import annotations

import threading

import pytest

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    PolicyContext,
    run_guarded_read,
    validate_query,
)
from django_mcp_guardrails.budgets import (
    CacheBudgetBackend,
    MemoryBudgetBackend,
    budget_key,
    enforce_budgets,
    filter_digest,
    set_budget_backend,
)
from django_mcp_guardrails.queries import NormalizedQuery


def _rows(count: int) -> list[dict[str, int]]:
    return [{"id": index} for index in range(count)]


def test_repeated_pages_share_a_filter_digest(read_policy: ModelReadPolicy) -> None:
    first = validate_query(read_policy, {"filters": {"name": "Acme"}, "page": 1})
    second = validate_query(read_policy, {"filters": {"name": "Acme"}, "page": 2})
    assert filter_digest(first) == filter_digest(second)
    context = PolicyContext.authenticated("user-1", client_id="client-a")
    assert budget_key(context, "search_items", first) == budget_key(
        context, "search_items", second
    )


def test_cumulative_rows_block_page_walking() -> None:
    policy = ModelReadPolicy(
        return_fields={"id"},
        max_limit=10,
        default_limit=10,
        max_session_rows=15,
        max_pages=10,
    )
    context = PolicyContext.authenticated("user-1")

    def producer(
        _context: PolicyContext, query: NormalizedQuery
    ) -> list[dict[str, int]]:
        return _rows(query.limit)

    first = run_guarded_read(policy, context, {"page": 1}, producer, tool_name="items")
    assert first.meta.count == 10
    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(policy, context, {"page": 2}, producer, tool_name="items")
    assert exc_info.value.code is ErrorCode.SESSION_BUDGET_EXCEEDED


def test_max_pages_blocks_deep_page_walk_through_the_engine() -> None:
    policy = ModelReadPolicy(
        return_fields={"id"},
        max_limit=5,
        default_limit=5,
        max_pages=2,
        max_session_rows=500,
    )
    context = PolicyContext.authenticated("user-1")

    def producer(
        _context: PolicyContext, _query: NormalizedQuery
    ) -> list[dict[str, int]]:
        return _rows(5)

    run_guarded_read(policy, context, {"page": 1}, producer, tool_name="items")
    run_guarded_read(policy, context, {"page": 2}, producer, tool_name="items")
    with pytest.raises(GuardrailError) as exc_info:
        run_guarded_read(policy, context, {"page": 3}, producer, tool_name="items")
    assert exc_info.value.code is ErrorCode.BULK_EXPORT_BLOCKED


def test_distinct_page_budget_blocks_additional_pages() -> None:
    policy = ModelReadPolicy(return_fields={"id"}, max_pages=2)
    context = PolicyContext.authenticated("user-1")
    empty = NormalizedQuery(filters=(), ordering=(), page=1, limit=1)
    enforce_budgets(policy, context, empty, tool_name="items", row_count=1)
    second = NormalizedQuery(filters=(), ordering=(), page=2, limit=1)
    enforce_budgets(policy, context, second, tool_name="items", row_count=1)
    third = NormalizedQuery(filters=(), ordering=(), page=3, limit=1)
    with pytest.raises(GuardrailError) as exc_info:
        enforce_budgets(policy, context, third, tool_name="items", row_count=1)
    assert exc_info.value.code is ErrorCode.BULK_EXPORT_BLOCKED


def test_budgets_are_isolated_by_user_and_filters(read_policy: ModelReadPolicy) -> None:
    policy = ModelReadPolicy(
        return_fields={"id"},
        filter_fields={"name"},
        max_limit=10,
        default_limit=10,
        max_session_rows=10,
    )

    def producer(
        _context: PolicyContext, _query: NormalizedQuery
    ) -> list[dict[str, int]]:
        return _rows(10)

    run_guarded_read(
        policy,
        PolicyContext.authenticated("user-1"),
        {"filters": {"name": "Acme"}},
        producer,
        tool_name="items",
    )
    other_user = run_guarded_read(
        policy,
        PolicyContext.authenticated("user-2"),
        {"filters": {"name": "Acme"}},
        producer,
        tool_name="items",
    )
    other_filter = run_guarded_read(
        policy,
        PolicyContext.authenticated("user-1"),
        {"filters": {"name": "Beta"}},
        producer,
        tool_name="items",
    )
    assert other_user.meta.count == 10
    assert other_filter.meta.count == 10


def test_memory_backend_serializes_concurrent_increments() -> None:
    backend = MemoryBudgetBackend()
    set_budget_backend(backend)
    policy = ModelReadPolicy(return_fields={"id"}, max_session_rows=20)
    context = PolicyContext.authenticated("user-1")
    query = NormalizedQuery(filters=(), ordering=(), page=1, limit=5)
    errors: list[GuardrailError] = []

    def worker() -> None:
        try:
            enforce_budgets(policy, context, query, tool_name="items", row_count=5)
        except GuardrailError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(errors) == 4
    assert all(error.code is ErrorCode.SESSION_BUDGET_EXCEEDED for error in errors)


def test_cache_backend_enforces_row_budgets() -> None:
    backend = CacheBudgetBackend()
    backend.reset()
    set_budget_backend(backend)
    policy = ModelReadPolicy(return_fields={"id"}, max_session_rows=3)
    context = PolicyContext.authenticated("user-1")
    query = NormalizedQuery(filters=(), ordering=(), page=1, limit=2)
    enforce_budgets(policy, context, query, tool_name="items", row_count=2)
    with pytest.raises(GuardrailError) as exc_info:
        enforce_budgets(policy, context, query, tool_name="items", row_count=2)
    assert exc_info.value.code is ErrorCode.SESSION_BUDGET_EXCEEDED


def test_cache_backend_counts_distinct_pages() -> None:
    backend = CacheBudgetBackend()
    backend.reset()
    set_budget_backend(backend)
    policy = ModelReadPolicy(return_fields={"id"}, max_pages=1)
    context = PolicyContext.authenticated("user-1")
    first = NormalizedQuery(filters=(), ordering=(), page=1, limit=1)
    enforce_budgets(policy, context, first, tool_name="items", row_count=1)
    second = NormalizedQuery(filters=(), ordering=(), page=2, limit=1)
    with pytest.raises(GuardrailError) as exc_info:
        enforce_budgets(policy, context, second, tool_name="items", row_count=1)
    assert exc_info.value.code is ErrorCode.BULK_EXPORT_BLOCKED
