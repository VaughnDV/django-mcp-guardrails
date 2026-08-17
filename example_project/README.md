# Example Django project

This directory is a **consumer** of `django-mcp-guardrails`, not a second package.

It demonstrates authenticated request context, an explicit tenant-scoped
read policy, and (later) a real MCP adapter without inventing a transport.

Create a user, an organization, and catalog items in Django admin after
migrate. The `OrganizationContextMiddleware` attaches `request.organization_id`
from the signed-in user's memberships—never from query parameters.

```bash
poetry run python example_project/manage.py mcp_guardrails_inventory
poetry run python example_project/manage.py mcp_guardrails_check
```

## Run locally

From the repository root, after `poetry install` and `cp .env.example .env`:

```bash
poetry run python example_project/manage.py check
poetry run python example_project/manage.py migrate
poetry run python example_project/manage.py runserver
```

Do not point this example at production databases or commit a real `DJANGO_SECRET_KEY`.
