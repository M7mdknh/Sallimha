from django.apps import AppConfig


class ConsoleConfig(AppConfig):
    name = "console"

    def ready(self):
        from console import schema  # noqa: F401 — registers the OpenAPI auth extension
