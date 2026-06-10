"""
Translate Board Games Companion (BGC) Hive backups into dune-tracker import dicts.

BGC stores BGG ids as board_game_id strings, player VP, and manual placement.
It does not track Dune leaders, alliances, or Sardaukar counts.
"""

from __future__ import annotations

import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from .bgc_hive import decode_playthrough, decode_score, load_players, read_box

DUNE_UPRISING_BGG = "397598"
DUNE_IMPERIUM_BGG = "316554"
DUNE_BLOODLINES_BGG = "426129"

BGC_IMPORT_PREFIX = "bgc-"


def extract_bgc_zip(zip_path: str | Path, dest: str | Path) -> Path:
    """Extract a BGC backup zip; returns destination directory."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    return dest


def _played_on(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def _import_key(playthrough_id: str) -> str:
    return f"{BGC_IMPORT_PREFIX}{playthrough_id}"


def games_from_bgc_directory(
    directory: str | Path,
    *,
    bgg_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Build import-ready game dicts from extracted .hive files.

    Each dict matches import_games_for_league() in sheet_io.py.
    """
    directory = Path(directory)
    allowed = set(bgg_ids) if bgg_ids is not None else {DUNE_UPRISING_BGG}
    players = load_players(directory / "players.hive")

    playthroughs = []
    for obj in read_box(directory / "playthroughs.hive").values():
        if isinstance(obj, dict):
            pt = decode_playthrough(obj)
            if pt and pt.get("board_game_id") in allowed:
                playthroughs.append(pt)

    scores_by_playthrough: dict[str, list[dict[str, Any]]] = {}
    for obj in read_box(directory / "scores.hive").values():
        if not isinstance(obj, dict):
            continue
        score = decode_score(obj)
        if not score or score.get("board_game_id") not in allowed:
            continue
        pt_id = score.get("playthrough_id")
        if pt_id:
            scores_by_playthrough.setdefault(pt_id, []).append(score)

    def _sort_key(pt: dict[str, Any]) -> tuple[str, str]:
        played = pt.get("played_at")
        if isinstance(played, datetime):
            played = played.isoformat()
        return (str(played or ""), str(pt["id"]))

    games: list[dict[str, Any]] = []
    for pt in sorted(playthroughs, key=_sort_key):
        pt_id = pt["id"]
        score_rows = scores_by_playthrough.get(pt_id, [])
        if not score_rows:
            continue

        results = []
        for score in sorted(
            score_rows,
            key=lambda s: (
                s.get("placement") if s.get("placement") is not None else 99,
                -(s.get("victory_points") or 0),
            ),
        ):
            player_id = score.get("player_id")
            name = players.get(player_id)
            if not name:
                continue
            vp = score.get("victory_points")
            if vp is None:
                continue
            results.append(
                {
                    "player": name,
                    "leader": "",
                    "victory_points": int(vp),
                }
            )

        if len(results) < 2:
            continue

        played_on = _played_on(pt.get("played_at"))
        if played_on is None:
            continue

        games.append(
            {
                "import_key": _import_key(pt_id),
                "played_on": played_on,
                "duration_minutes": pt.get("duration_minutes"),
                "rounds": None,
                "results": results,
                "bgc_board_game_id": pt.get("board_game_id"),
                "bgc_playthrough_id": pt_id,
            }
        )

    return games


def games_from_bgc_zip(
    zip_path: str | Path,
    *,
    bgg_ids: Iterable[str] | None = None,
    extract_to: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Extract zip (optional) and return translated games."""
    zip_path = Path(zip_path)
    if extract_to:
        directory = extract_bgc_zip(zip_path, extract_to)
    else:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            directory = extract_bgc_zip(zip_path, tmp)
            return games_from_bgc_directory(directory, bgg_ids=bgg_ids)
    return games_from_bgc_directory(directory, bgg_ids=bgg_ids)
