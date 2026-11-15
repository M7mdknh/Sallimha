from django.urls import path

from core import views_health

urlpatterns = [
    path("healthz", views_health.healthz),
    path("readyz", views_health.readyz),
]
