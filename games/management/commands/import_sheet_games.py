from django.core.management.base import BaseCommand, CommandError

from games.data.liga_n1 import LIGA_N1_GAMES
from games.integrations.sheet_io import import_games_for_league
from games.models import League


class Command(BaseCommand):
    help = "Import historical games from the bundled Liga N°1 sheet data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--league",
            default="liga-n1",
            help="League slug (default: liga-n1 for «Liga N°1»).",
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
                f'League with slug "{slug}" not found. Create «Liga N°1» first or pass --league.'
            ) from exc

        created, skipped = import_games_for_league(
            league,
            LIGA_N1_GAMES,
            dry_run=options["dry_run"],
        )
        prefix = "Would create" if options["dry_run"] else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {created} game(s) in «{league.name}» ({skipped} already imported)."
            )
        )
