# Example Django project

This directory is a **consumer** of `django-mcp-guardrails`, not a second package.

It exists so later milestones can demonstrate authenticated request context, explicit read policies, and a real MCP adapter without inventing a transport.

## Run locally

From the repository root, after `poetry install` and `cp .env.example .env`:

```bash
poetry run python example_project/manage.py check
poetry run python example_project/manage.py migrate
poetry run python example_project/manage.py runserver
```

Do not point this example at production databases or commit a real `DJANGO_SECRET_KEY`.
