"""
Pull live league data from the Cloudflare Worker API into the local Django DB.

Used when direct Postgres (Neon) is unreachable from the dev machine but the
Worker can still reach the database.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from games.data.worker_neon_snapshot import (
    NEON_HITOS,
    NEON_HITO_MANUAL_PLAYERS,
    NEON_MEMBERSHIPS,
)
from games.models import Game, GameResult, League, LeagueHito, LeagueMembership, Player


_WORKER_DT = re.compile(
    r"^(?P<dow>\w{3}) (?P<mon>\w{3}) (?P<day>\d{1,2}) (?P<year>\d{4}) "
    r"(?P<hms>\d{2}:\d{2}:\d{2})"
)


def parse_worker_datetime(value: str) -> datetime:
    """Parse Worker JS Date.toString() timestamps."""
    value = (value or "").strip()
    if not value:
        return timezone.now()
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    match = _WORKER_DT.match(value)
    if not match:
        raise ValueError(f"Unrecognized datetime: {value!r}")
    text = (
        f"{match['mon']} {match['day']} {match['year']} "
        f"{match['hms']} +0000"
    )
    return datetime.strptime(text, "%b %d %Y %H:%M:%S %z")


def parse_played_on(value: str) -> date:
    return date.fromisoformat(value)


def fetch_json(url: str, api_key: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "dune-tracker-sync/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def fetch_league_detail(base_url: str, api_key: str, slug: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/leagues/{slug}"
    return fetch_json(url, api_key)


def use_sqlite_database(base_dir) -> None:
    from django.conf import settings
    from django.db import connections

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": base_dir / "db.sqlite3",
    }
    connections.close_all()


def _clear_games_data() -> None:
    LeagueHito.manual_players.through.objects.all().delete()
    GameResult.objects.all().delete()
    Game.objects.all().delete()
    LeagueHito.objects.all().delete()
    LeagueMembership.objects.all().delete()
    League.objects.all().delete()
    Player.objects.all().delete()


def _reset_sqlite_sequence(table: str, max_pk: int) -> None:
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s", [table])
        if max_pk:
            cursor.execute(
                "INSERT INTO sqlite_sequence (name, seq) VALUES (%s, %s)",
                [table, max_pk],
            )


@transaction.atomic
def import_from_worker(
    base_url: str,
    api_key: str,
    *,
    clear: bool = True,
) -> dict[str, int]:
    """Replace local games data with Worker / Neon snapshot."""
    league_rows = fetch_json(f"{base_url.rstrip('/')}/api/leagues", api_key)
    players = fetch_json(f"{base_url.rstrip('/')}/api/players", api_key)
    league_details = [
        fetch_league_detail(base_url, api_key, row["slug"]) for row in league_rows
    ]
    casual_games = fetch_json(
        f"{base_url.rstrip('/')}/api/games?casual=1",
        api_key,
    )
    casual_details: list[dict[str, Any]] = []
    for row in casual_games:
        game_id = row["id"]
        casual_details.append(
            fetch_json(f"{base_url.rstrip('/')}/api/games/{game_id}", api_key)
        )

    if clear:
        _clear_games_data()

    for row in players:
        Player.objects.create(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            created_at=parse_worker_datetime(row.get("created_at", "")),
        )

    for row in league_rows:
        detail = next(d for d in league_details if d["id"] == row["id"])
        League.objects.create(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row.get("description") or "",
            scoring_notes=row.get("scoring_notes") or "",
            scoring_config=row.get("scoring_config") or {},
            created_at=parse_worker_datetime(row.get("created_at", "")),
        )

    for row in NEON_MEMBERSHIPS:
        LeagueMembership.objects.create(
            id=row["id"],
            league_id=row["league_id"],
            player_id=row["player_id"],
            joined_at=parse_worker_datetime(row["joined_at"]),
        )

    for row in NEON_HITOS:
        LeagueHito.objects.create(
            id=row["id"],
            league_id=row["league_id"],
            slug=row["slug"],
            name=row["name"],
            description=row["description"],
            metric=row["metric"],
            order=row["order"],
            is_builtin=row["is_builtin"],
            is_active=row["is_active"],
            manual_value=row["manual_value"],
            manual_player_id=row["manual_player_id"],
            created_at=timezone.now(),
        )

    through = LeagueHito.manual_players.through
    for hito_id, player_id in NEON_HITO_MANUAL_PLAYERS:
        through.objects.create(leaguehito_id=hito_id, player_id=player_id)

    game_count = 0
    result_count = 0
    designated_updates: list[tuple[int, int | None]] = []

    all_games: list[dict[str, Any]] = []
    for detail in league_details:
        all_games.extend(detail.get("games", []))
    all_games.extend(casual_details)

    for game_row in all_games:
        game = Game.objects.create(
            id=game_row["id"],
            league_id=game_row["league_id"],
            played_on=parse_played_on(game_row["played_on"]),
            base_game=game_row["base_game"],
            bloodlines=bool(game_row.get("bloodlines")),
            player_count=game_row["player_count"],
            rounds=game_row.get("rounds"),
            duration_minutes=game_row.get("duration_minutes"),
            notes=game_row.get("notes") or "",
            tied_game=bool(game_row.get("tied_game")),
            placement_tiebreaks=game_row.get("placement_tiebreaks") or {},
            created_at=parse_worker_datetime(game_row.get("created_at", "")),
        )
        game_count += 1
        designated_updates.append((game.pk, game_row.get("designated_winner_id")))

        for result_row in game_row.get("results", []):
            GameResult.objects.create(
                id=result_row["id"],
                game_id=game.pk,
                player_id=result_row["player_id"],
                leader=result_row.get("leader") or "",
                victory_points=result_row["victory_points"],
                sardaukar_count=int(result_row.get("sardaukar_count") or 0),
                alliance_emperor=bool(result_row.get("alliance_emperor")),
                alliance_guild=bool(result_row.get("alliance_guild")),
                alliance_bene_gesserit=bool(result_row.get("alliance_bene_gesserit")),
                alliance_fremen=bool(result_row.get("alliance_fremen")),
                order=int(result_row.get("order") or 0),
            )
            result_count += 1

    for game_id, winner_result_id in designated_updates:
        if winner_result_id:
            Game.objects.filter(pk=game_id).update(
                designated_winner_id=winner_result_id
            )

    max_ids = {
        Player: max((p["id"] for p in players), default=0),
        League: max((l["id"] for l in league_rows), default=0),
        LeagueMembership: max((m["id"] for m in NEON_MEMBERSHIPS), default=0),
        LeagueHito: max((h["id"] for h in NEON_HITOS), default=0),
        Game: max((g["id"] for g in all_games), default=0),
        GameResult: max(
            (r["id"] for g in all_games for r in g.get("results", [])),
            default=0,
        ),
    }
    for model, max_pk in max_ids.items():
        _reset_sqlite_sequence(model._meta.db_table, max_pk)

    return {
        "players": len(players),
        "leagues": len(league_rows),
        "memberships": len(NEON_MEMBERSHIPS),
        "hitos": len(NEON_HITOS),
        "games": game_count,
        "results": result_count,
    }
