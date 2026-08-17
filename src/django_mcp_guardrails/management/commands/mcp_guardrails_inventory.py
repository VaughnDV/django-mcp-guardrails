"""Inventory of registered guarded tools."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from django_mcp_guardrails.policies import ModelReadPolicy
from django_mcp_guardrails.registry import get_registry


class Command(BaseCommand):
    help = "Print a machine-readable inventory of guarded MCP tools."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--format",
            choices=("json", "text"),
            default="text",
            dest="output_format",
        )

    def handle(self, *args: object, **options: object) -> None:
        payload = [_describe(name, policy) for name, policy in get_registry().items()]
        if options.get("output_format") == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        if not payload:
            self.stdout.write("No guarded tools are registered.")
            return
        for item in payload:
            self.stdout.write(
                f"{item['name']} risk={item['risk']} version={item['policy_version']}"
            )
            fields = item["return_fields"]
            field_list = ", ".join(fields) if isinstance(fields, list) else ""
            self.stdout.write(f"  return_fields={field_list or '(none)'}")
            self.stdout.write(f"  max_limit={item['max_limit']}")


def _describe(name: str, policy: object) -> dict[str, object]:
    data: dict[str, object] = {
        "name": name,
        "risk": str(getattr(policy, "risk", "read")),
        "policy_version": getattr(policy, "version", ""),
        "enabled": getattr(policy, "enabled", False),
        "return_fields": sorted(getattr(policy, "return_fields", ())),
        "max_limit": getattr(policy, "max_limit", None),
        "authentication": "trusted_request_context",
    }
    if isinstance(policy, ModelReadPolicy):
        data["filter_fields"] = sorted(policy.filter_fields)
        data["ordering_fields"] = sorted(policy.ordering_fields)
        data["relation_paths"] = sorted(policy.relation_paths)
        data["has_scoped_queryset"] = policy.queryset is not None
    return data
