"""Release gate for a staging/production host (ADR-0004), run after migrations and before traffic:

    manage.py deploy_check [--allow-blocked]

Each line is PASS, FAIL or BLOCKED. BLOCKED marks an external input that has not been supplied yet (for example the
WhatsApp sender); it fails the gate unless --allow-blocked is given. Values are never printed, only whether they
are present and acceptable.
"""

from django.conf import settings
from django.core import checks
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Check that this deployment is safe to receive traffic (PASS/FAIL/BLOCKED)."

    def add_arguments(self, parser):
        parser.add_argument("--allow-blocked", action="store_true",
                            help="exit successfully when the only problems are missing external inputs")

    def handle(self, *args, allow_blocked=False, **options):
        results = [*self._config(), self._django_checks(), self._database(), self._worker(), self._media(),
                   self._whatsapp()]
        report = "\n".join(f"{status} {name}: {detail}" for status, name, detail in results)
        failed = any(status == "FAIL" for status, _n, _d in results)
        blocked = any(status == "BLOCKED" for status, _n, _d in results)
        if failed or (blocked and not allow_blocked):
            raise CommandError(f"deploy check did not pass\n{report}")
        return report

    def _config(self):
        deployed = settings.ENVIRONMENT in {"staging", "production"} and not settings.IS_DEV
        yield ("PASS" if deployed else "FAIL", "environment", f"SALLIMHA_ENV={settings.ENVIRONMENT}")
        unsafe = [name for name, bad in (("DEBUG", settings.DEBUG), ("SIMULATOR_ENABLED", settings.SIMULATOR_ENABLED),
                                         ("fake WhatsApp transport", settings.WHATSAPP_TRANSPORT == "fake")) if bad]
        yield ("FAIL" if unsafe else "PASS", "demo features", ", ".join(unsafe) or "off")
        weak = [name for name, value, minimum in (("DJANGO_SECRET_KEY", settings.SECRET_KEY, 50),
                                                   ("HASH_KEY", settings.HASH_KEY, 32))
                if len(value or "") < minimum or value.startswith("dev-only")]
        yield ("FAIL" if weak else "PASS", "secrets", f"too short or development values: {', '.join(weak)}"
               if weak else "present (values not shown)")
        hosts_ok = settings.ALLOWED_HOSTS and not {"localhost", "127.0.0.1", "*"} & set(settings.ALLOWED_HOSTS)
        origins = settings.CSRF_TRUSTED_ORIGINS
        origins_ok = origins and all(o.startswith("https://") for o in origins)
        yield ("PASS" if hosts_ok and origins_ok else "FAIL", "hosts",
               "public host names over https" if hosts_ok and origins_ok else
               "set DJANGO_ALLOWED_HOSTS and https DJANGO_CSRF_TRUSTED_ORIGINS")

    def _django_checks(self):
        problems = [m for m in checks.run_checks(include_deployment_checks=True)
                    if m.level >= checks.WARNING and m.id not in settings.SILENCED_SYSTEM_CHECKS]
        return ("FAIL" if problems else "PASS", "django check --deploy",
                ", ".join(sorted({m.id for m in problems})) or "clean")

    def _database(self):
        try:
            executor = MigrationExecutor(connection)
            pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        except Exception as exc:  # noqa: BLE001 - reported as a failed check
            return ("FAIL", "database", f"unreachable ({type(exc).__name__})")
        return ("FAIL", "database", f"{len(pending)} migrations not applied") if pending else \
            ("PASS", "database", "reachable, migrations applied")

    def _worker(self):
        from core.views_health import worker_status

        status = worker_status()
        return ("PASS" if status == "ok" else "FAIL", "worker", f"heartbeat {status}")

    def _media(self):
        from ops.services.media import storage_check

        if settings.MEDIA_STORAGE != "s3":
            return ("FAIL", "media", "use a private S3-compatible bucket (MEDIA_STORAGE=s3), not local files")
        result = storage_check()
        return ("PASS" if result == "ok" else "FAIL", "media", f"private bucket write/read/delete {result}")

    def _whatsapp(self):
        missing = [name for name, value in (("WHATSAPP_ACCESS_TOKEN", settings.WHATSAPP_ACCESS_TOKEN),
                                             ("WHATSAPP_PHONE_NUMBER_ID", settings.WHATSAPP_PHONE_NUMBER_ID),
                                             ("WHATSAPP_APP_SECRET", settings.WHATSAPP_APP_SECRET),
                                             ("WHATSAPP_VERIFY_TOKEN", settings.WHATSAPP_VERIFY_TOKEN)) if not value]
        return ("BLOCKED" if missing else "PASS", "whatsapp",
                f"not supplied: {', '.join(missing)}" if missing else "sender configured (not yet exercised)")
