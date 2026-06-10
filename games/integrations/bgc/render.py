"""Render bundled BGC import Python modules."""

from games.integrations.bgc.io import DUNE_UPRISING_BGG


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


def render_module(games: list[dict], *, source: str, leaders_synced: bool = False) -> str:
    body = "\n".join(_format_game(g) for g in games)
    if leaders_synced:
        leaders_line = (
            "Leaders may be synced from live DB via "
            "`python manage.py sync_bgc_leaders`."
        )
    else:
        leaders_line = (
            "Leaders, alliances, and Sardaukar were not tracked in BGC "
            "and are left empty."
        )
    return f'''"""
Historical Dune: Imperium — Uprising games imported from Board Games Companion.

Source: {source}
BGG id: {DUNE_UPRISING_BGG}
Games: {len(games)}

Imported via `python manage.py import_bgc_games`; idempotent by import_key.
{leaders_line}
"""

from datetime import date

BGC_UPRISING_GAMES = [
{body}
]
'''
