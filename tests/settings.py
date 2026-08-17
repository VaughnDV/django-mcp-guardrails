"""Isolated Django settings for unit tests. These require no secrets or network."""

from __future__ import annotations

SECRET_KEY = "test-secret-key-not-for-production"
DEBUG = True
USE_TZ = True
USE_I18N = True

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_mcp_guardrails",
    "tests.testapp",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

ROOT_URLCONF = "tests.urls"

MIDDLEWARE: list[str] = []

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "django-mcp-guardrails-tests",
    }
}
