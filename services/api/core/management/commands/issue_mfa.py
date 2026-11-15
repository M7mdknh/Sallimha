"""Bootstrap/rotate TOTP enrolment for a console user from the server (e.g. the first super admin).
Prints the provisioning URI once; deliver it out of band. Audited."""

from django.core.management.base import BaseCommand, CommandError

from console import mfa
from core.audit import audit
from ops.models import Staff


class Command(BaseCommand):
    help = "Issue (or rotate) TOTP enrolment for a console user; prints the provisioning URI once."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        staff = Staff.objects.filter(user__username=username).first()
        if staff is None:
            raise CommandError("unknown console user")
        Staff.objects.filter(pk=staff.pk).update(session_epoch=staff.session_epoch + 1)
        uri = mfa.issue_secret(staff)
        audit("staff.mfa_issue", actor_id=None, actor_label="server-operator", channel="system",
              entity_type="staff", entity_id=staff.id)
        self.stdout.write(uri)
