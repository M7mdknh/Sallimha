from django.urls import path

from core import views_health
from messaging.webhook import whatsapp_webhook

urlpatterns = [
    path("healthz", views_health.healthz),
    path("readyz", views_health.readyz),
    path("webhooks/whatsapp", whatsapp_webhook),
]
