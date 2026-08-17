"""Smoke tests for package import, version metadata, and Django app loading."""

from __future__ import annotations

import sys
from importlib import metadata
from io import StringIO

from django.apps import apps
from django.core.management import call_command

import django_mcp_guardrails


def test_version_matches_package_metadata() -> None:
    assert django_mcp_guardrails.__version__ == metadata.version(
        "django-mcp-guardrails"
    )


def test_public_package_exports_only_version() -> None:
    assert django_mcp_guardrails.__all__ == ["__version__"]


def test_core_does_not_import_optional_frameworks() -> None:
    imported = {"mcp", "django_mcp_server"} & set(sys.modules)
    assert not imported


def test_optional_adapter_modules_import_without_extras() -> None:
    import django_mcp_guardrails.adapters.django_mcp_server as django_mcp_server_adapter
    import django_mcp_guardrails.adapters.mcp_sdk as mcp_sdk_adapter

    assert django_mcp_server_adapter.__doc__
    assert mcp_sdk_adapter.__doc__


def test_app_config_is_installed() -> None:
    config = apps.get_app_config("django_mcp_guardrails")
    assert config.name == "django_mcp_guardrails"
    assert apps.is_installed("django_mcp_guardrails")


def test_django_system_checks_pass() -> None:
    call_command("check", stdout=StringIO())
