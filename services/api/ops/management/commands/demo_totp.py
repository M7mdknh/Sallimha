"""Print the current TOTP code for a synthetic demo account (local/test only)."""

import pyotp
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ops.management.commands.seed_demo import DEMO_TOTP_SECRETS


class Command(BaseCommand):
    help = "Print the current second-factor code for the demo manager/admin (local/test only)."

    def add_arguments(self, parser):
        parser.add_argument("username", choices=sorted(DEMO_TOTP_SECRETS))

    def handle(self, *args, username, **options):
        if not settings.IS_DEV:
            raise CommandError("demo_totp is only available in local/test environments")
        self.stdout.write(pyotp.TOTP(DEMO_TOTP_SECRETS[username]).now())
