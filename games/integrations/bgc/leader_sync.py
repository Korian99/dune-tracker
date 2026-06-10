"""Sync leader fields from live league data into bundled BGC import games."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from games.integrations.sheet_io import IMPORT_NOTE_PREFIX


def parse_import_key_from_notes(notes: str) -> str | None:
    """Return import key from ``import_key=...`` notes, or None."""
    notes = (notes or "").strip()
    if not notes.startswith(IMPORT_NOTE_PREFIX):
        return None
    key = notes[len(IMPORT_NOTE_PREFIX) :].strip()
    return key or None


def _find_live_result(
    live_results: list[dict[str, Any]],
    player: str,
    victory_points: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Match a bundled result row to a live result by name, then VP."""
    by_name = {r["player_name"]: r for r in live_results}
    if player in by_name:
        return by_name[player], None

    by_vp: dict[int, list[dict[str, Any]]] = {}
    for row in live_results:
        by_vp.setdefault(row["victory_points"], []).append(row)
    matches = by_vp.get(victory_points, [])
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, f"ambiguous VP {victory_points} for player {player!r}"
    return None, f"no live result for player {player!r} (VP {victory_points})"


def merge_leaders_into_games(
    games_data: list[dict[str, Any]],
    live_games: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    """
    Copy non-empty leaders from live games into bundled import rows.

    Games match on import_key. Result rows match by player name first,
    then victory_points within the same game.
    """
    live_by_key = {g["import_key"]: g for g in live_games}
    update_count = 0
    warnings: list[str] = []

    for game in games_data:
        import_key = game.get("import_key")
        if not import_key:
            warnings.append("bundled game missing import_key")
            continue

        live_game = live_by_key.get(import_key)
        if live_game is None:
            warnings.append(f"no live game for import_key={import_key}")
            continue

        live_results = live_game.get("results") or []
        for row in game.get("results") or []:
            player = row.get("player", "")
            vp = row.get("victory_points")
            if vp is None:
                continue

            live_row, warn = _find_live_result(live_results, player, int(vp))
            if warn:
                warnings.append(f"{import_key}: {warn}")
                continue
            if live_row is None:
                continue

            leader = (live_row.get("leader") or "").strip()
            if not leader:
                continue

            current = (row.get("leader") or "").strip()
            if current == leader:
                continue

            row["leader"] = leader
            update_count += 1

    return update_count, warnings


def fetch_league_from_worker(
    base_url: str,
    api_key: str,
    league_slug: str,
) -> dict[str, Any]:
    """GET /api/leagues/{slug} from the Cloudflare Worker API."""
    base = base_url.rstrip("/")
    url = f"{base}/api/leagues/{league_slug}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "dune-tracker-sync/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() if exc.fp else ""
        raise RuntimeError(f"API error {exc.code}: {body}") from exc


def live_games_from_worker_league(league: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize Worker league JSON games into live_games format."""
    live: list[dict[str, Any]] = []
    for game in league.get("games") or []:
        import_key = parse_import_key_from_notes(game.get("notes", ""))
        if not import_key:
            continue
        live.append(
            {
                "import_key": import_key,
                "notes": game.get("notes", ""),
                "results": [
                    {
                        "player_name": row["player_name"],
                        "leader": row.get("leader", ""),
                        "victory_points": row["victory_points"],
                    }
                    for row in game.get("results") or []
                ],
            }
        )
    return live


def live_games_from_db(league_slug: str) -> list[dict[str, Any]]:
    """Load BGC-imported games and results from the Django ORM."""
    from games.models import Game, League

    league = League.objects.get(slug=league_slug)
    live: list[dict[str, Any]] = []
    games = (
        Game.objects.filter(league=league, notes__startswith=IMPORT_NOTE_PREFIX)
        .prefetch_related("results__player")
        .order_by("played_on", "id")
    )
    for game in games:
        import_key = parse_import_key_from_notes(game.notes)
        if not import_key:
            continue
        live.append(
            {
                "import_key": import_key,
                "notes": game.notes,
                "results": [
                    {
                        "player_name": result.player.name,
                        "leader": result.leader,
                        "victory_points": result.victory_points,
                    }
                    for result in game.results.all()
                ],
            }
        )
    return live
