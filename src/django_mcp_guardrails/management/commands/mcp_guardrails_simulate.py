"""Run a policy against a normalized request without invoking the tool."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from django_mcp_guardrails.budgets import filter_digest
from django_mcp_guardrails.errors import GuardrailError
from django_mcp_guardrails.queries import query_digest_shape, validate_query
from django_mcp_guardrails.registry import get_registry


class Command(BaseCommand):
    help = "Validate a query against a registered policy without executing it."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument("tool_name")
        parser.add_argument(
            "query_json",
            nargs="?",
            default="{}",
            help="JSON object using the guarded query vocabulary.",
        )

    def handle(self, *args: object, **options: object) -> None:
        name = str(options["tool_name"])
        try:
            raw = json.loads(str(options["query_json"]))
        except json.JSONDecodeError as exc:
            raise CommandError("query_json must be valid JSON.") from exc
        if not isinstance(raw, dict):
            raise CommandError("query_json must be an object.")
        try:
            policy = get_registry().get(name)
            query = validate_query(policy, raw)
        except GuardrailError as exc:
            raise CommandError(exc.message) from exc
        payload = {
            "tool": name,
            "query": query_digest_shape(query),
            "digest": filter_digest(query),
            "limit": query.limit,
            "page": query.page,
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
