from django.urls import include, path, re_path

from core import views_console, views_health
from messaging.webhook import whatsapp_webhook

urlpatterns = [
    path("healthz", views_health.healthz),
    path("readyz", views_health.readyz),
    path("webhooks/whatsapp", whatsapp_webhook),
    path("api/", include("console.urls")),
    # Last: any other GET path is a console route (never api/, webhooks/, health or built assets).
    re_path(r"^(?!api/|webhooks/|healthz$|readyz$|assets/|brand/|static/).*$", views_console.console_index),
]
