from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default = True
    name = "catalog"
    verbose_name = "Example catalog"

    def ready(self) -> None:
        from catalog import policies as _policies

        _ = _policies
