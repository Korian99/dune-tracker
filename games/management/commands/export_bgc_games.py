"""Export BGC Hive backup games into a bundled Python data module."""

from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from games.bgc_io import DUNE_UPRISING_BGG, games_from_bgc_directory, games_from_bgc_zip


def _format_game(game: dict) -> str:
    lines = [
        "    {",
        f'        "import_key": "{game["import_key"]}",',
        f"        \"played_on\": date({game['played_on'].year}, {game['played_on'].month}, {game['played_on'].day}),",
    ]
    if game.get("duration_minutes") is not None:
        lines.append(f'        "duration_minutes": {game["duration_minutes"]},')
    if game.get("rounds") is not None:
        lines.append(f'        "rounds": {game["rounds"]},')
    lines.append('        "results": [')
    for row in game["results"]:
        parts = [
            f'"player": "{row["player"]}"',
            f'"leader": "{row["leader"]}"',
            f'"victory_points": {row["victory_points"]}',
        ]
        if row.get("bgc_placement") is not None:
            parts.append(f'"bgc_placement": {row["bgc_placement"]}')
        lines.append("            {" + ", ".join(parts) + "},")
    lines.append("        ],")
    lines.append("    },")
    return "\n".join(lines)


def render_module(games: list[dict], *, source: str) -> str:
    body = "\n".join(_format_game(g) for g in games)
    return f'''"""
Historical Dune: Imperium — Uprising games imported from Board Games Companion.

Source: {source}
BGG id: {DUNE_UPRISING_BGG}
Games: {len(games)}

Imported via `python manage.py import_bgc_games`; idempotent by import_key.
Leaders, alliances, and Sardaukar were not tracked in BGC and are left empty.
"""

from datetime import date

BGC_UPRISING_GAMES = [
{body}
]
'''


class Command(BaseCommand):
    help = "Translate a BGC backup zip or extracted folder into games/data/bgc_uprising_import.py."

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            help="Path to BGC backup .zip or extracted folder with .hive files.",
        )
        parser.add_argument(
            "-o",
            "--output",
            default="games/data/bgc_uprising_import.py",
            help="Output Python module path (default: games/data/bgc_uprising_import.py).",
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
