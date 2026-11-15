from django.apps import AppConfig


class OpsConfig(AppConfig):
    name = "ops"

    def ready(self):
        from core.worker import register_step
        from ops.services import dispatch

        register_step(20, "expire_offers", dispatch.expire_offers)
        register_step(30, "dispatch", dispatch.dispatch_all)
        register_step(40, "alerts", dispatch.raise_alerts)
