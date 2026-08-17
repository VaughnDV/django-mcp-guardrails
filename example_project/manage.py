#!/usr/bin/env python
"""Django's command-line utility for the example project."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    src = repo_root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "example_project.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Install the project with `poetry install` "
            "and use `poetry run python example_project/manage.py`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
