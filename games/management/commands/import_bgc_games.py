from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from games.bgc_io import games_from_bgc_directory, games_from_bgc_zip
from games.data.bgc_uprising_import import BGC_UPRISING_GAMES
from games.models import League
from games.sheet_io import import_games_for_league


class Command(BaseCommand):
    help = "Import Dune Uprising games from bundled BGC export or a fresh backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--league",
            default="liga-n0",
            help="League slug to import into (default: liga-n0 for «Liga N°0»).",
        )
        parser.add_argument(
            "--source",
            help="Optional BGC .zip or extracted folder; defaults to bundled bgc_uprising_import.py.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many games would be created without writing.",
        )

    def handle(self, *args, **options):
        slug = options["league"]
        try:
            league = League.objects.get(slug=slug)
        except League.DoesNotExist as exc:
            raise CommandError(
                f'League with slug "{slug}" not found. Create the league first or pass --league.'
            ) from exc

        source = options.get("source")
        if source:
            path = Path(source)
            if not path.exists():
                raise CommandError(f"Source not found: {path}")
            if path.is_dir():
                games_data = games_from_bgc_directory(path)
            else:
                games_data = games_from_bgc_zip(path)
        else:
            games_data = BGC_UPRISING_GAMES

        created, skipped = import_games_for_league(
            league,
            games_data,
            dry_run=options["dry_run"],
        )
        prefix = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {created} game(s) in «{league.name}» ({skipped} already imported)."
            )
        )
