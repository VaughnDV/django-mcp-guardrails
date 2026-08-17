"""Optional privacy-safe audit persistence."""

from __future__ import annotations

from django.db import models


class AuditEvent(models.Model):
    """Decision metadata only. Never store prompts, results, or secrets."""

    tool_name = models.CharField(max_length=128)
    policy_version = models.CharField(max_length=32)
    user_id = models.CharField(max_length=64, blank=True)
    organization_id = models.CharField(max_length=64, blank=True)
    client_id = models.CharField(max_length=64, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True)
    started_at = models.DateTimeField()
    duration_ms = models.PositiveIntegerField()
    status = models.CharField(max_length=32)
    error_code = models.CharField(max_length=64, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    serialized_bytes = models.PositiveIntegerField(default=0)
    truncated = models.BooleanField(default=False)
    request_digest = models.CharField(max_length=64)
    filter_fields = models.JSONField(default=list)

    class Meta:
        app_label = "django_mcp_guardrails"
        ordering = ("-started_at",)

    def __str__(self) -> str:
        return f"{self.tool_name} {self.status}"
