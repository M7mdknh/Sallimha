"""The controlled procedure for an admin's sign-in (ADR-0012, docs/runbooks/admin-access.md).

Run on the server by the technical owner — never available in the app. Sets up or recovers an admin's access:
first access after promotion, a locked second factor, a lost phone or a suspected compromise. Two named people
(a requesting admin and a different approving supervisor or admin), a reason, and the password and second factor
reset together; every session of that person ends. The setup code and the second-factor link are printed once, for
the person in person. Names given here are the operator's attestation; the record is visible on the Team page."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.errors import DomainError
from ops.services import staffdir


def _person(identifier: str, what: str):
    staff = staffdir.find_by_identifier(identifier)
    if staff is None:
        raise CommandError(f"{what}: no staff account signs in as {identifier!r}")
    return staff


class Command(BaseCommand):
    help = "Controlled admin access (ADR-0012): two named people, password and second factor reset together."

    def add_arguments(self, parser):
        parser.add_argument("target", help="The admin's sign-in name (mobile number or username)")
        parser.add_argument("--requested-by", help="Sign-in name of the enabled admin asking (may be the target)")
        parser.add_argument("--approved-by", help="Sign-in name of a different enabled supervisor or admin")
        parser.add_argument("--first-admin", action="store_true",
                            help="Only for the organisation's very first admin, when nobody else could approve")
        parser.add_argument("--reason", required=True, help="Why, and how the person's identity was checked")
        parser.add_argument("--operator", required=True, help="Your name: the person running this on the server")

    def handle(self, *args, target, requested_by, approved_by, first_admin, reason, operator, **options):
        person = _person(target, "target")
        requester = _person(requested_by, "--requested-by") if requested_by else None
        approver = _person(approved_by, "--approved-by") if approved_by else None
        if not first_admin and (requester is None or approver is None):
            raise CommandError("--requested-by and --approved-by are required (or --first-admin)")
        try:
            code, uri = staffdir.grant_admin_access(person, requested_by=requester, approved_by=approver,
                                                    reason=reason, operator=operator, first_admin=first_admin)
        except DomainError as err:
            raise CommandError(err.code) from err
        expires = timezone.localtime(timezone.now() + staffdir.SETUP_TTL).strftime("%Y-%m-%d %H:%M %Z")
        self.stdout.write("Give these to the person in person; they are shown only once and never stored.")
        self.stdout.write(f"Sign-in name: {person.user.username}")
        self.stdout.write(f"Setup code (valid until {expires}): {code}")
        self.stdout.write(f"Second factor (scan into an authenticator app): {uri}")
