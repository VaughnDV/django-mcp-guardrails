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
        """Defer side effects until Django is ready.

        System checks and policy registration will be wired here in later
        milestones. This method must stay free of database queries, network
        clients, and settings access that is not yet available.
        """
