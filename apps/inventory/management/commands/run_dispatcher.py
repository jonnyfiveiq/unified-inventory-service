"""
Management command to start the dispatcherd background task service.

Usage:
    python manage.py run_dispatcher

This starts the asyncio-based dispatcherd service that listens on the
``inventory_tasks`` pg_notify channel and executes collection tasks in
a subprocess worker pool.

In the Kind cluster this runs as a sidecar container or a separate
Deployment with the same image but a different entrypoint:

    CMD ["uv", "run", "--no-sync", "python", "manage.py", "run_dispatcher"]
"""

import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger("apps.inventory.dispatcher")


class Command(BaseCommand):
    help = "Start the dispatcherd background task worker for inventory collection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-workers",
            type=int,
            default=None,
            help="Override the maximum number of worker subprocesses (default: from config).",
        )

    def handle(self, *args, **options):
        # Ensure dispatcherd is configured (should already be from apps.py ready())
        from apps.inventory.dispatcher import setup_dispatcher

        setup_dispatcher()

        try:
            from dispatcherd.config import settings as dispatcher_settings

            if options["max_workers"]:
                dispatcher_settings.service["pool_kwargs"]["max_workers"] = options["max_workers"]
        except ImportError:
            self.stderr.write(self.style.ERROR("dispatcherd is not installed. Install with: pip install dispatcherd[pg_notify]"))
            return

        # Force-import the tasks module so @task decorators register
        import apps.inventory.tasks  # noqa: F401

        self.stdout.write(self.style.SUCCESS("Starting dispatcherd worker for inventory_tasks channel..."))

        from dispatcherd import run_service

        run_service()
