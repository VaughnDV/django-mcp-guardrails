"""Fail CI when registered policies have high-severity findings."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from django_mcp_guardrails.checks import check_policies


class Command(BaseCommand):
    help = "Run django-mcp-guardrails policy checks and fail on errors."

    def handle(self, *args: object, **options: object) -> None:
        messages = check_policies()
        errors = [message for message in messages if message.level >= 40]
        for message in messages:
            self.stdout.write(str(message))
        if errors:
            raise CommandError(f"{len(errors)} high-severity policy finding(s).")
        self.stdout.write("No high-severity policy findings.")
