"""Django request context, scoped QuerySets, and object-permission tests."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from tests.testapp.models import CatalogItem, Industry, Organization

from django_mcp_guardrails import (
    ErrorCode,
    GuardrailError,
    ModelReadPolicy,
    PolicyContext,
    execute_model_read,
    guarded_tool,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def factory() -> RequestFactory:
    return RequestFactory()


@pytest.fixture
def tenants() -> dict[str, Organization]:
    alpha = Organization.objects.create(name="Alpha")
    beta = Organization.objects.create(name="Beta")
    return {"alpha": alpha, "beta": beta}


@pytest.fixture
def industry() -> Industry:
    return Industry.objects.create(name="Tech")


@pytest.fixture
def catalog_items(
    tenants: dict[str, Organization], industry: Industry
) -> dict[str, CatalogItem]:
    shared_name = "Acme Widget"
    alpha_item = CatalogItem.objects.create(
        organization=tenants["alpha"],
        industry=industry,
        name=shared_name,
        status="active",
        secret_note="alpha-secret",
    )
    beta_item = CatalogItem.objects.create(
        organization=tenants["beta"],
        industry=industry,
        name=shared_name,
        status="active",
        secret_note="beta-secret",
    )
    extra = CatalogItem.objects.create(
        organization=tenants["alpha"],
        industry=industry,
        name="Other",
        status="archived",
        secret_note="alpha-other",
    )
    return {"alpha": alpha_item, "beta": beta_item, "extra": extra}


def _policy_for(organization: Organization, **overrides: object) -> ModelReadPolicy:
    defaults = {
        "model": CatalogItem,
        "queryset": lambda request: CatalogItem.objects.filter(
            organization_id=request.organization_id
        ),
        "return_fields": {"id", "name", "status", "industry"},
        "filter_fields": {"name", "status"},
        "ordering_fields": {"name", "id"},
        "relation_paths": {"industry"},
        "nested_return_fields": {"industry": {"id", "name"}},
        "lookups": {"name": {"exact", "icontains"}, "status": {"exact", "in"}},
        "default_limit": 25,
        "max_limit": 100,
    }
    defaults.update(overrides)
    return ModelReadPolicy(**defaults)  # type: ignore[arg-type]


def _request_for(
    factory: RequestFactory,
    user: User,
    organization: Organization,
) -> object:
    request = factory.get("/mcp")
    request.user = user
    request.organization_id = organization.pk
    return request


def test_from_request_uses_trusted_user_not_query_args(
    factory: RequestFactory, tenants: dict[str, Organization]
) -> None:
    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    assert context.is_authenticated
    assert context.user_id == user.pk
    assert context.organization_id == tenants["alpha"].pk


def test_inactive_user_is_not_authenticated(
    factory: RequestFactory, tenants: dict[str, Organization]
) -> None:
    user = User.objects.create_user("inactive", password="x", is_active=False)
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(request)
    assert context.is_authenticated is False
    assert context.user_id is None


def test_anonymous_request_is_not_authenticated(factory: RequestFactory) -> None:
    request = factory.get("/mcp")
    request.user = AnonymousUser()
    context = PolicyContext.from_request(request)
    assert context.is_authenticated is False


def test_tenant_scope_applied_before_filters(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    policy = _policy_for(tenants["alpha"])
    envelope = execute_model_read(policy, context, {"filters": {"name": "Acme Widget"}})
    ids = {item["id"] for item in envelope.items}
    assert catalog_items["alpha"].pk in ids
    assert catalog_items["beta"].pk not in ids
    assert all("secret_note" not in item for item in envelope.items)


def test_other_tenant_looks_like_empty_not_not_found(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    user = User.objects.create_user("beta-user", password="x")
    request = _request_for(factory, user, tenants["beta"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    policy = _policy_for(tenants["beta"])
    envelope = execute_model_read(
        policy,
        context,
        {"filters": {"name": "no-such-item-in-any-tenant"}},
    )
    assert envelope.items == ()
    assert "CatalogItem" not in envelope.to_dict().__str__()


def test_disallowed_relation_still_rejected_before_orm(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    policy = _policy_for(tenants["alpha"])
    with pytest.raises(GuardrailError) as exc_info:
        execute_model_read(
            policy, context, {"filters": {"organization.secret_note": "x"}}
        )
    assert exc_info.value.code is ErrorCode.FIELD_NOT_ALLOWED


def test_queryset_evaluates_once(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    policy = _policy_for(tenants["alpha"])
    with CaptureQueriesContext(connection) as captured:
        execute_model_read(policy, context, {"limit": 10})
    selects = [
        query["sql"]
        for query in captured.captured_queries
        if query["sql"].lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 1


def test_object_permission_filters_rows(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    allowed_id = catalog_items["alpha"].pk

    def only_primary(ctx: PolicyContext, obj: CatalogItem) -> bool:
        return obj.pk == allowed_id

    policy = _policy_for(tenants["alpha"], object_permission=only_primary)
    envelope = execute_model_read(policy, context, {})
    assert [item["id"] for item in envelope.items] == [allowed_id]


def test_guarded_tool_uses_scoped_queryset(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    policy = _policy_for(tenants["alpha"])

    @guarded_tool(policy=policy, name="search_items")
    def search_items(
        _context: PolicyContext, _query: object
    ) -> list[dict[str, object]]:
        raise AssertionError("queryset path must not call the producer")

    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    envelope = search_items(context, {"filters": {"status": "active"}})
    names = {item["name"] for item in envelope.items}
    assert names == {"Acme Widget"}
    assert catalog_items["extra"].name not in names


def test_limit_is_applied_before_returning_rows(
    factory: RequestFactory,
    tenants: dict[str, Organization],
    catalog_items: dict[str, CatalogItem],
) -> None:
    user = User.objects.create_user("alpha-user", password="x")
    request = _request_for(factory, user, tenants["alpha"])
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    policy = _policy_for(tenants["alpha"], default_limit=1, max_limit=1)
    envelope = execute_model_read(policy, context, {})
    assert envelope.meta.count == 1
    assert envelope.meta.has_more is True
