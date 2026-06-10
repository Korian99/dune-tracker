"""
Import/export games in the pipe-delimited Google Sheets format.

Bonus columns (10 / 12 / 15 / early-win) are derived at scoring time, not stored.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

from collections import defaultdict

from django.db import transaction

from games.models import Game, GameResult, League, resolve_player
from games.services.leaders import LEADER_NAMES
from games.services.scoring import _has_highest_vp, resolve_scoring_config
from games.services.tiebreak import apply_tiebreak

IMPORT_NOTE_PREFIX = "import_key="

ALLIANCE_EXPORT_KEYS = ("EMP", "SG", "BG", "FRE")
ALLIANCE_FIELD_MAP = {
    "EMP": "alliance_emperor",
    "SG": "alliance_guild",
    "BG": "alliance_bene_gesserit",
    "FRE": "alliance_fremen",
}

SHEET_HEADER = (
    "Datos||Resultado||Pos.||Jugador||Líder||Score||10||12||15||-7||"
    "EMP||SG||BG||FRE||Sardaukars"
)
SHEET_SEPARATOR = "-" * 113


def parse_sheet_date(value: str) -> date:
    """Parse d/m/yy or d/m/yyyy from the sheet."""
    value = (value or "").strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {value!r}")


def parse_duration_minutes(value: str) -> int | None:
    """Parse H:MM duration from the sheet."""
    value = (value or "").strip()
    if not value:
        return None
    match = re.match(r"^(\d+):(\d{1,2})$", value)
    if not match:
        raise ValueError(f"Invalid duration: {value!r}")
    hours, minutes = int(match.group(1)), int(match.group(2))
    return hours * 60 + minutes


def format_duration_minutes(minutes: int | None) -> str:
    if not minutes:
        return ""
    hours, mins = divmod(minutes, 60)
    return f"{hours}:{mins:02d}"


def format_sheet_date(d: date) -> str:
    return f"{d.day}/{d.month}/{d.year % 100:02d}"


def parse_bool(value: str) -> bool:
    return (value or "").strip().upper() == "TRUE"


def format_bool(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def import_note_key(key: str) -> str:
    return f"{IMPORT_NOTE_PREFIX}{key}"


def _result_defaults() -> dict[str, Any]:
    return {
        "alliance_emperor": False,
        "alliance_guild": False,
        "alliance_bene_gesserit": False,
        "alliance_fremen": False,
        "sardaukar_count": 0,
    }


def _normalize_result_row(row: dict[str, Any]) -> dict[str, Any]:
    merged = {**_result_defaults(), **row}
    for field in ALLIANCE_FIELD_MAP.values():
        merged[field] = bool(merged.get(field))
    merged["sardaukar_count"] = int(merged.get("sardaukar_count") or 0)
    leader = (merged.get("leader") or "").strip()
    if leader and leader not in LEADER_NAMES:
        raise ValueError(f"Unknown leader: {leader!r}")
    merged["leader"] = leader
    return merged


def game_already_imported(league: League, import_key: str) -> bool:
    marker = import_note_key(import_key)
    return Game.objects.filter(league=league, notes__contains=marker).exists()


def apply_bgc_placements(game: Game, results_data: list[dict[str, Any]]) -> None:
    """
    Resolve VP ties using BGC manual placement (bgc_placement per result row).
    """
    by_name = {r.player.name: r for r in game.results.select_related("player")}
    by_vp: dict[int, list[tuple[int, GameResult]]] = defaultdict(list)
    for row in results_data:
        placement = row.get("bgc_placement")
        if placement is None:
            continue
        result = by_name.get(row["player"])
        if result is None:
            continue
        by_vp[result.victory_points].append((int(placement), result))

    for vp, items in by_vp.items():
        if len(items) < 2:
            continue
        order = [r.pk for _, r in sorted(items, key=lambda x: (x[0], x[1].pk))]
        apply_tiebreak(game, "rank", order_result_ids=order, vp=vp)
    game.refresh_from_db()


@transaction.atomic
def import_games_for_league(
    league: League,
    games_data: Iterable[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Create games from structured dicts. Returns (created, skipped).
    """
    created = 0
    skipped = 0
    for game_data in games_data:
        import_key = game_data["import_key"]
        if game_already_imported(league, import_key):
            skipped += 1
            continue
        if dry_run:
            created += 1
            continue

        game = Game.objects.create(
            league=league,
            played_on=game_data["played_on"],
            base_game=Game.BaseGame.UPRISING,
            bloodlines=True,
            player_count=len(game_data["results"]),
            rounds=game_data.get("rounds"),
            duration_minutes=game_data.get("duration_minutes"),
            notes=import_note_key(import_key),
        )
        for order, raw in enumerate(game_data["results"]):
            row = _normalize_result_row(raw)
            player = resolve_player(row["player"], league=league)
            GameResult.objects.create(
                game=game,
                player=player,
                leader=row["leader"],
                victory_points=row["victory_points"],
                sardaukar_count=row["sardaukar_count"],
                alliance_emperor=row["alliance_emperor"],
                alliance_guild=row["alliance_guild"],
                alliance_bene_gesserit=row["alliance_bene_gesserit"],
                alliance_fremen=row["alliance_fremen"],
                order=order,
            )
        if any(r.get("bgc_placement") is not None for r in game_data["results"]):
            apply_bgc_placements(game, game_data["results"])
        created += 1
    return created, skipped


def _bonus_flags(result: GameResult, league: League | None) -> tuple[bool, bool, bool, bool]:
    """Return sheet columns 10, 12, 15, early-win (-7) for export."""
    vp = result.victory_points
    if not league:
        return (vp >= 10, vp >= 12, vp >= 15, False)
    config = resolve_scoring_config(league)
    thresholds = set(config.get("vp_thresholds") or [])
    early = False
    max_round = int(config.get("early_win_max_round") or 0)
    if max_round > 0 and _has_highest_vp(result):
        rounds = result.game.rounds
        if rounds is not None and 1 <= rounds <= max_round:
            early = True
    return (
        10 in thresholds and vp >= 10,
        12 in thresholds and vp >= 12,
        15 in thresholds and vp >= 15,
        early,
    )


def _result_row_parts(pos: int, result: GameResult, league: League | None) -> list[str]:
    b10, b12, b15, early = _bonus_flags(result, league)
    parts = [
        str(pos),
        result.player.name,
        result.leader or "",
        str(result.victory_points),
        format_bool(b10),
        format_bool(b12),
        format_bool(b15),
        format_bool(early),
    ]
    for key in ALLIANCE_EXPORT_KEYS:
        field = ALLIANCE_FIELD_MAP[key]
        parts.append(format_bool(getattr(result, field)))
    parts.append(str(result.sardaukar_count))
    return parts


def export_game_block(game: Game) -> list[str]:
    """One game block in Google Sheets pipe format."""
    league = game.league
    results = sorted(
        game.results.select_related("player"),
        key=lambda r: (-r.victory_points, r.order, r.id),
    )
    lines = [SHEET_HEADER]
    meta_rows = [
        ("Fecha", format_sheet_date(game.played_on)),
        ("Rondas", str(game.rounds or "")),
        ("Tiempo", format_duration_minutes(game.duration_minutes)),
        ("Vacio", ""),
    ]
    for idx, (label, value) in enumerate(meta_rows):
        result = results[idx]
        parts = ["Datos", label, value] + _result_row_parts(idx + 1, result, league)
        lines.append("||".join(parts))

    return lines


def export_league_sheet(league: League) -> str:
    """Full export for a league: games separated by sheet dividers."""
    games = (
        Game.objects.filter(league=league)
        .prefetch_related("results__player")
        .order_by("played_on", "id")
    )
    blocks: list[str] = []
    for game in games:
        if blocks:
            blocks.append(SHEET_SEPARATOR)
        blocks.extend(export_game_block(game))
    return "\n".join(blocks) + ("\n" if blocks else "")
