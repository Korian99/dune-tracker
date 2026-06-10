"""Export BGC Hive backup games into a bundled Python data module."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from games.integrations.bgc.io import (
    DUNE_UPRISING_BGG,
    games_from_bgc_directory,
    games_from_bgc_zip,
)
from games.integrations.bgc.render import render_module


class Command(BaseCommand):
    help = "Translate a BGC backup zip or extracted folder into games/data/bgc_uprising.py."

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            help="Path to BGC backup .zip or extracted folder with .hive files.",
        )
        parser.add_argument(
            "-o",
            "--output",
            default="games/data/bgc_uprising.py",
            help="Output Python module path (default: games/data/bgc_uprising.py).",
        )

    def handle(self, *args, **options):
        source = Path(options["source"])
        if not source.exists():
            raise CommandError(f"Source not found: {source}")

        if source.is_dir():
            games = games_from_bgc_directory(source)
        else:
            games = games_from_bgc_zip(source)

        if not games:
            raise CommandError("No Dune Uprising games found in the backup.")

        out = Path(options["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_module(games, source=str(source)), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {len(games)} game(s) to {out}")
        )
