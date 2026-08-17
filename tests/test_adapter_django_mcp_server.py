"""django-mcp-server adapter contract tests."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from tests.testapp.models import CatalogItem, Industry, Organization

from django_mcp_guardrails import ErrorCode, ModelReadPolicy, PolicyContext
from django_mcp_guardrails.adapters.contract import (
    assert_output_is_bounded_and_sanitized,
    assert_tools_are_listed_deterministically,
    assert_unauthenticated_is_denied,
)

pytestmark = [pytest.mark.django_db, pytest.mark.adapter]


def _framework_available() -> bool:
    try:
        from django_mcp_guardrails.adapters.django_mcp_server import (
            assert_supported_django_mcp_server,
        )

        assert_supported_django_mcp_server()
        return True
    except Exception:
        return False


pytestmark.append(
    pytest.mark.skipif(
        not _framework_available(), reason="django-mcp-server extra is not available"
    )
)


class _LocalServer:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def add_tool(self, fn: Any, name: str, description: str) -> None:
        self.tools[name] = fn


class _Driver:
    def __init__(self, server: _LocalServer, request: object | None) -> None:
        self.server = server
        self.request = request

    def list_tool_names(self) -> list[str]:
        return sorted(self.server.tools)

    def call(
        self, name: str, context: PolicyContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        return self.call_raw(name, context, arguments)

    def call_raw(
        self, name: str, context: PolicyContext, arguments: dict[str, Any]
    ) -> Any:
        from django_mcp_guardrails.adapters.django_mcp_server import _import_django_mcp

        django_request_ctx, _server = _import_django_mcp()
        token = django_request_ctx.set(context.request)
        try:
            return self.server.tools[name](arguments)
        finally:
            django_request_ctx.reset(token)


@pytest.fixture
def mcp_env(factory: RequestFactory) -> dict[str, Any]:
    from django_mcp_guardrails.adapters.django_mcp_server import (
        register_guarded_model_tool,
    )

    alpha = Organization.objects.create(name="Alpha")
    beta = Organization.objects.create(name="Beta")
    industry = Industry.objects.create(name="Tech")
    CatalogItem.objects.create(
        organization=alpha, industry=industry, name="Acme Widget", secret_note="alpha"
    )
    CatalogItem.objects.create(
        organization=beta, industry=industry, name="Acme Widget", secret_note="beta"
    )
    user = User.objects.create_user("alpha-user", password="x")
    request = factory.get("/mcp")
    request.user = user
    request.organization_id = alpha.pk
    policy = ModelReadPolicy(
        model=CatalogItem,
        queryset=lambda req: CatalogItem.objects.filter(
            organization_id=req.organization_id
        ),
        return_fields={"id", "name", "status"},
        filter_fields={"name", "status"},
        default_limit=25,
        max_limit=100,
    )
    server = _LocalServer()
    register_guarded_model_tool(
        policy=policy,
        name="search_items",
        mcp_server=server,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    register_guarded_model_tool(
        policy=policy,
        name="list_items",
        mcp_server=server,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    context = PolicyContext.from_request(
        request,
        get_organization_id=lambda req: getattr(req, "organization_id", None),
    )
    return {
        "driver": _Driver(server, request),
        "context": context,
        "request": request,
        "alpha": alpha,
        "beta": beta,
        "server": server,
    }


def test_supported_version_is_accepted() -> None:
    from django_mcp_guardrails.adapters.django_mcp_server import (
        assert_supported_django_mcp_server,
    )

    assert assert_supported_django_mcp_server().startswith("0.5.")


def test_unsupported_version_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    from django_mcp_guardrails.adapters import django_mcp_server as adapter

    monkeypatch.setattr(adapter, "version", lambda _name: "9.0.0")
    with pytest.raises(adapter.AdapterUnavailable, match="not supported"):
        adapter.assert_supported_django_mcp_server()


def test_contract_tool_listing(mcp_env: dict[str, Any]) -> None:
    assert_tools_are_listed_deterministically(mcp_env["driver"])


def test_contract_unauthenticated(mcp_env: dict[str, Any]) -> None:
    assert_unauthenticated_is_denied(
        mcp_env["driver"],
        "search_items",
        PolicyContext.anonymous(),
    )


def test_contract_bounded_sanitized_output(mcp_env: dict[str, Any]) -> None:
    assert_output_is_bounded_and_sanitized(
        mcp_env["driver"], "search_items", mcp_env["context"]
    )


def test_tenant_isolation_through_adapter(mcp_env: dict[str, Any]) -> None:
    result = mcp_env["driver"].call("search_items", mcp_env["context"], {})
    names = {item["name"] for item in result["items"]}
    assert names == {"Acme Widget"}
    for item in result["items"]:
        assert "secret_note" not in item
        assert item["id"]


def test_adapter_errors_use_stable_codes(mcp_env: dict[str, Any]) -> None:
    from django_mcp_guardrails.adapters.django_mcp_server import MCPGuardrailError

    with pytest.raises(MCPGuardrailError) as exc_info:
        mcp_env["driver"].call(
            "search_items",
            mcp_env["context"],
            {"filters": {"secret_note": "alpha"}},
        )
    payload = exc_info.value.to_mcp_payload()
    assert payload["code"] == str(ErrorCode.FIELD_NOT_ALLOWED)
    assert "secret_note" not in payload["message"]


def test_missing_request_context_is_unauthenticated(mcp_env: dict[str, Any]) -> None:
    from django_mcp_guardrails.adapters.django_mcp_server import MCPGuardrailError

    with pytest.raises(MCPGuardrailError) as exc_info:
        mcp_env["server"].tools["search_items"]({})
    assert exc_info.value.code is ErrorCode.UNAUTHENTICATED
