"""Copy production data from the Cloudflare Worker API into local SQLite."""

import os
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from games.integrations.worker_sync import import_from_worker, use_sqlite_database


class Command(BaseCommand):
    help = (
        "Replace local SQLite games data with a snapshot from the Worker API "
        "(same Neon DB as production). Use when DATABASE_URL cannot connect locally."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--api-url",
            default=os.environ.get("DUNE_API_URL", "").strip(),
            help="Worker base URL (or set DUNE_API_URL).",
        )
        parser.add_argument(
            "--api-key",
            default=os.environ.get("DUNE_API_KEY", "").strip(),
            help="Worker bearer token (or set DUNE_API_KEY).",
        )
        parser.add_argument(
            "--keep-postgres",
            action="store_true",
            help="Do not switch DATABASES to SQLite before importing.",
        )

    def handle(self, *args, **options):
        api_url = (options["api_url"] or "").strip()
        api_key = (options["api_key"] or "").strip()
        if not api_url or not api_key:
            raise CommandError(
                "Set --api-url and --api-key, or DUNE_API_URL and DUNE_API_KEY in the environment."
            )

        if not options["keep_postgres"]:
            use_sqlite_database(Path(settings.BASE_DIR))
            self.stdout.write("Using local db.sqlite3")

        call_command("migrate", verbosity=0, interactive=False)

        counts = import_from_worker(api_url, api_key)
        self.stdout.write(
            self.style.SUCCESS(
                "Synced from Worker: "
                + ", ".join(f"{k}={v}" for k, v in counts.items())
            )
        )
        self.stdout.write(
            "Tip: comment out DATABASE_URL in .env so runserver uses SQLite."
        )
