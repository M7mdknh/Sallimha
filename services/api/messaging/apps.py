from django.apps import AppConfig


class MessagingConfig(AppConfig):
    name = "messaging"

    def ready(self):
        from core.worker import register_step
        from messaging import inbound, outbox

        register_step(10, "inbox", inbound.process_inbox)
        register_step(90, "outbox", outbox.send_due)
