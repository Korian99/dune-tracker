from django.core.management.base import BaseCommand, CommandError

from games.models import League
from games.integrations.sheet_io import export_league_sheet


class Command(BaseCommand):
    help = "Export league games to Google Sheets pipe-delimited format (stdout)."

    def add_arguments(self, parser):
        parser.add_argument(
            "league",
            nargs="?",
            default="liga-n1",
            help="League slug (default: liga-n1).",
        )
        parser.add_argument(
            "-o",
            "--output",
            help="Write to this file instead of stdout.",
        )

    def handle(self, *args, **options):
        slug = options["league"]
        try:
            league = League.objects.get(slug=slug)
        except League.DoesNotExist as exc:
            raise CommandError(f'League with slug "{slug}" not found.') from exc

        text = export_league_sheet(league)
        if options["output"]:
            with open(options["output"], "w", encoding="utf-8") as fh:
                fh.write(text)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exported {league.games.count()} game(s) to {options['output']}"
                )
            )
        else:
            self.stdout.write(text)
