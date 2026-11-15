from django.conf import settings
from django.urls import path

from console import views
from messaging import simulator_api

urlpatterns = [
    path("auth/csrf", views.csrf),
    path("auth/login", views.login_view),
    path("auth/logout", views.logout_view),
    path("auth/me", views.me),
    path("events/", views.events),
    path("events/<int:event_id>/live", views.event_live),
    path("events/<int:event_id>/shifts", views.StartShift.as_view()),
    path("shifts/<int:shift_id>/end", views.EndShift.as_view()),
    path("alerts/<int:alert_id>/ack", views.AckAlert.as_view()),
    path("tickets/<int:ticket_id>", views.ticket_detail),
    path("tickets/<int:ticket_id>/cancel", views.CancelTicket.as_view()),
    path("tickets/<int:ticket_id>/withdraw", views.WithdrawRequest.as_view()),
    path("tickets/<int:ticket_id>/withdraw-with-custody", views.WithdrawWithCustody.as_view()),
    path("tickets/<int:ticket_id>/custody-transfer", views.TransferCustody.as_view()),
    path("tickets/<int:ticket_id>/intake-transfer", views.TransferIntake.as_view()),
    path("tickets/<int:ticket_id>/correct-phone", views.CorrectPhone.as_view()),
    path("tickets/<int:ticket_id>/confirm-receipt", views.ConfirmReceipt.as_view()),
    path("tickets/<int:ticket_id>/except-intake", views.ExceptIntake.as_view()),
    path("media/<int:media_id>", views.media_file),
]

if settings.SIMULATOR_ENABLED:  # local/test only; settings refuse it elsewhere
    urlpatterns += [
        path("dev/sim/phones", simulator_api.phones),
        path("dev/sim/messages", simulator_api.messages),
        path("dev/sim/send", simulator_api.send),
    ]
