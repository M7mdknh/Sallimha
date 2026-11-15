import logging
import os
import signal
import socket

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection

from core import worker

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Sallimha worker: inbox, outbox, offer deadlines, dispatch and alerts (ADR-0002)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="run a single pass and exit")
        parser.add_argument("--id", default="", help="worker id for the heartbeat")
        parser.add_argument("--poll", type=float, default=1.0, help="max seconds between passes")

    def handle(self, *args, once=False, id="", poll=1.0, **options):  # noqa: A002
        worker_id = id or f"{socket.gethostname()}-{os.getpid()}"
        if once:
            worker.run_once(worker_id=worker_id)
            return
        stopping = {"flag": False}

        def stop(*_):
            stopping["flag"] = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        log.info("worker %s started", worker_id)
        listening = False
        while not stopping["flag"]:
            try:
                if not listening:
                    connection.ensure_connection()
                    with connection.cursor() as cursor:
                        cursor.execute("LISTEN sallimha_work")
                    listening = True
                worker.run_once(worker_id=worker_id)
                # NOTIFY is only a wake-up hint; the poll timeout is the guarantee (ADR-0002).
                for _ in connection.connection.notifies(timeout=poll, stop_after=1):
                    pass
            except Exception:  # noqa: BLE001 — keep the worker alive; state is durable
                log.exception("worker pass failed")
                listening = False
                close_old_connections()
                connection.close()
                signal.sigtimedwait([signal.SIGTERM, signal.SIGINT], 1.0) if hasattr(signal, "sigtimedwait") else None
        log.info("worker %s stopped", worker_id)
