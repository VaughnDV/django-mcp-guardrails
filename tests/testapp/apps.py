from django.apps import AppConfig


class TestAppConfig(AppConfig):
    default = True
    name = "tests.testapp"
    label = "testapp"
    verbose_name = "Guardrails test app"
