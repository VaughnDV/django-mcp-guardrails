"""Django application configuration for django-mcp-guardrails."""

from django.apps import AppConfig


class DjangoMCPGuardrailsConfig(AppConfig):
    """App config. Import-time setup must not query the database or settings."""

    default = True
    default_auto_field = "django.db.models.AutoField"
    name = "django_mcp_guardrails"
    label = "django_mcp_guardrails"
    verbose_name = "Django MCP Guardrails"

    def ready(self) -> None:
        """Register system checks. Do not query the database here."""
        from django_mcp_guardrails.checks import register_checks

        register_checks()
