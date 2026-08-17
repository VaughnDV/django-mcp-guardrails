"""Fail CI when registered policies have high-severity findings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.checks import CheckMessage
from django.core.management.base import BaseCommand, CommandError

from django_mcp_guardrails.checks import check_policies


class Command(BaseCommand):
    help = "Run django-mcp-guardrails policy checks and fail on errors."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--baseline",
            default=None,
            help="JSON file of known findings to ignore while adopting the package.",
        )

    def handle(self, *args: object, **options: object) -> None:
        messages = check_policies()
        ignored = _load_baseline(options.get("baseline"))
        remaining = [
            message for message in messages if not _is_ignored(message, ignored)
        ]
        errors = [message for message in remaining if message.level >= 40]
        for message in messages:
            prefix = "ignored " if _is_ignored(message, ignored) else ""
            self.stdout.write(f"{prefix}{message}")
        if errors:
            raise CommandError(f"{len(errors)} high-severity policy finding(s).")
        self.stdout.write("No high-severity policy findings.")


def _load_baseline(path_value: object) -> list[dict[str, Any]]:
    if path_value is None:
        return []
    path = Path(str(path_value))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError("Baseline file must be readable JSON.") from exc
    ignored = payload.get("ignored", payload) if isinstance(payload, dict) else payload
    if not isinstance(ignored, list):
        raise CommandError("Baseline file must contain an ignored list.")
    return [item for item in ignored if isinstance(item, dict)]


def _is_ignored(message: CheckMessage, ignored: list[dict[str, Any]]) -> bool:
    msg_id = message.id
    msg_obj = None if message.obj is None else str(message.obj)
    for item in ignored:
        if item.get("id") != msg_id:
            continue
        if "obj" not in item:
            return True
        if item.get("obj") == msg_obj:
            return True
    return False
