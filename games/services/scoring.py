"""
League scoring for Dune Tracker.

Config lives in League.scoring_config (JSON). Use resolve_scoring_config() for
merged defaults. Edit parameters per league in the league form or admin.

Default standard system:
  - Best count_games results count toward standings (default 8; 0 = all games).
  - Placement points by rank (default 1st=5, 2nd=3, 3rd=2, 4th=1).
  - +1 early-win if max VP and rounds 1..early_win_max_round (default 6).
  - +1 per vp_threshold reached (default 10, 12, 15; stacking).

Alternate: {"system": "victory_points"} — league points = VP per game (still best-N).
"""

import re
from collections import defaultdict
from typing import Any, TypedDict

from .defaults import DEFAULT_LEAGUE_SCORING_NOTES, default_league_scoring_config
from games.models import GameResult, League

DEFAULT_SCORING_NOTES = DEFAULT_LEAGUE_SCORING_NOTES


def default_scoring_config() -> dict[str, Any]:
    """Alias for migrations/tests; placement keys normalized on read."""
    raw = default_league_scoring_config()
    return {
        **raw,
        "placement_points": {int(k): int(v) for k, v in raw["placement_points"].items()},
    }


def parse_vp_thresholds_input(raw: str) -> list[int]:
    """Parse comma/space-separated VP thresholds (1–20); sorted unique ascending."""
    text = (raw or "").strip()
    if not text:
        return []
    values: list[int] = []
    for part in re.split(r"[,;\s]+", text):
        if not part:
            continue
        try:
            value = int(part)
        except ValueError as exc:
            raise ValueError(f"«{part}» no es un número válido.") from exc
        if value < 1 or value > 20:
            raise ValueError("Cada umbral debe estar entre 1 y 20 PV.")
        values.append(value)
    return sorted(set(values))


def format_vp_thresholds_display(thresholds: list[int]) -> str:
    return ", ".join(str(t) for t in thresholds)


def resolve_scoring_config(league: League) -> dict[str, Any]:
    """Merge league.scoring_config onto defaults; normalize types from JSON."""
    merged = {**default_scoring_config(), **(league.scoring_config or {})}
    raw_pp = merged.get("placement_points") or default_scoring_config()["placement_points"]
    merged["placement_points"] = {int(k): int(v) for k, v in raw_pp.items()}
    merged["vp_thresholds"] = [int(x) for x in merged.get("vp_thresholds", [10, 12, 15])]
    merged["count_games"] = int(merged.get("count_games", 8))
    merged["early_win_max_round"] = int(merged.get("early_win_max_round", 6))
    merged["system"] = merged.get("system") or "standard"
    return merged


def config_from_form_data(cleaned: dict) -> dict[str, Any]:
    """Build scoring_config JSON from LeagueForm cleaned_data."""
    thresholds = cleaned.get("_vp_thresholds_parsed")
    if thresholds is None:
        thresholds = parse_vp_thresholds_input(cleaned.get("vp_thresholds", ""))
    return {
        "system": "standard",
        "count_games": cleaned["count_games"],
        "placement_points": {
            1: cleaned["points_1st"],
            2: cleaned["points_2nd"],
            3: cleaned["points_3rd"],
            4: cleaned["points_4th"],
        },
        "early_win_max_round": cleaned["early_win_max_round"],
        "vp_thresholds": thresholds,
    }


def config_to_form_initial(config: dict[str, Any]) -> dict[str, Any]:
    cfg = {**default_scoring_config(), **config}
    pp = cfg["placement_points"]
    thresholds = [int(x) for x in cfg.get("vp_thresholds", [])]
    return {
        "count_games": cfg["count_games"],
        "points_1st": pp.get(1, 5),
        "points_2nd": pp.get(2, 3),
        "points_3rd": pp.get(3, 2),
        "points_4th": pp.get(4, 1),
        "early_win_max_round": cfg["early_win_max_round"],
        "vp_thresholds": format_vp_thresholds_display(thresholds),
    }


class LeaguePointsBreakdown(TypedDict):
    placement: int
    placement_points: int
    early_win: int
    vp_threshold_bonuses: int
    total: float


def _config_system(config: dict[str, Any]) -> str:
    return config.get("system") or "standard"


def _winner_pk_for_game(game, game_results: list[GameResult]) -> int | None:
    """Winner pk without extra queries when game_results are already loaded."""
    if game.tied_game:
        return None
    if game.designated_winner_id:
        return game.designated_winner_id
    if not game_results:
        return None
    max_vp = max(r.victory_points for r in game_results)
    leaders = [r for r in game_results if r.victory_points == max_vp]
    if len(leaders) == 1:
        return leaders[0].pk
    return None


def build_game_scoring_context(results) -> dict[int, dict[str, Any]]:
    """Per-game max VP, winner, tie flag, and rounds for bulk scoring."""
    by_game: dict[int, list[GameResult]] = defaultdict(list)
    for result in results:
        by_game[result.game_id].append(result)

    ctx: dict[int, dict[str, Any]] = {}
    for game_id, game_results in by_game.items():
        game = game_results[0].game
        max_vp = max(r.victory_points for r in game_results)
        ctx[game_id] = {
            "max_vp": max_vp,
            "winner_pk": _winner_pk_for_game(game, game_results),
            "tied_game": game.tied_game,
            "rounds": game.rounds,
        }
    return ctx


def _has_highest_vp(
    result: GameResult,
    game_ctx: dict[str, Any] | None = None,
) -> bool:
    """True if this result qualifies for the early-win bonus."""
    if game_ctx is None:
        max_vp = (
            result.game.results.order_by("-victory_points")
            .values_list("victory_points", flat=True)
            .first()
        )
        if max_vp is None or result.victory_points != max_vp:
            return False
        game = result.game
        if game.tied_game:
            return False
        winner = game.resolved_winner()
        if winner is not None:
            return result.pk == winner.pk
        return True

    if game_ctx["tied_game"] or result.victory_points != game_ctx["max_vp"]:
        return False
    winner_pk = game_ctx["winner_pk"]
    if winner_pk is not None:
        return result.pk == winner_pk
    return True


def _vp_threshold_bonuses(vp: int, thresholds: list[int]) -> int:
    return sum(1 for t in thresholds if vp >= t)


def compute_league_points_breakdown(
    result: GameResult,
    league: League,
    *,
    placement: int | None = None,
    game_ctx: dict[str, Any] | None = None,
) -> LeaguePointsBreakdown:
    """
    Per-game league points with components.

    Ties (placement): placements_for_game() in tiebreak.py — each resolved
    VP group gives one player the better rank; declared ties share a rank.
    Early-win: designated winner only; unresolved VP ties use all at max VP.
    """
    config = resolve_scoring_config(league)

    if placement is None:
        placement = result.placement

    if _config_system(config) == "victory_points":
        vp = float(result.victory_points)
        return LeaguePointsBreakdown(
            placement=placement,
            placement_points=0,
            early_win=0,
            vp_threshold_bonuses=0,
            total=vp,
        )

    placement_pts = config["placement_points"].get(placement, 0)

    early_win = 0
    max_round = config["early_win_max_round"]
    if max_round > 0 and _has_highest_vp(result, game_ctx):
        rounds = game_ctx["rounds"] if game_ctx is not None else result.game.rounds
        if rounds is not None and 1 <= rounds <= max_round:
            early_win = 1

    vp = result.victory_points
    vp_bonuses = _vp_threshold_bonuses(vp, config["vp_thresholds"])

    total = float(placement_pts + early_win + vp_bonuses)
    return LeaguePointsBreakdown(
        placement=placement,
        placement_points=placement_pts,
        early_win=early_win,
        vp_threshold_bonuses=vp_bonuses,
        total=total,
    )


def compute_league_points(result: GameResult, league: League) -> float:
    """Points earned by one player in one game under league rules."""
    return compute_league_points_breakdown(result, league)["total"]


def breakdown_display(breakdown: LeaguePointsBreakdown) -> str:
    """Compact formula for templates, e.g. 5+1+2=8."""
    parts = [str(breakdown["placement_points"])]
    if breakdown["early_win"]:
        parts.append("1")
    if breakdown["vp_threshold_bonuses"]:
        parts.append(str(breakdown["vp_threshold_bonuses"]))
    total = breakdown["total"]
    total_str = str(int(total)) if total == int(total) else str(total)
    return "+".join(parts) + f"={total_str}"


def league_score_rows_for_game(game, league: League) -> list[dict[str, Any]]:
    """League points per result row for game detail / league game cards."""
    rows = []
    for result in game.results.select_related("player"):
        breakdown = compute_league_points_breakdown(result, league)
        total = breakdown["total"]
        rows.append(
            {
                "result": result,
                "breakdown": breakdown,
                "formula": breakdown_display(breakdown),
                "total": total,
            }
        )
    return rows


def game_score_summary(game, league: League) -> list[dict[str, Any]]:
    """Per-player league scoring for one game, sorted by placement."""
    rows = []
    for row in league_score_rows_for_game(game, league):
        result = row["result"]
        total = row["total"]
        rows.append(
            {
                "result": result,
                "player_name": result.player.name,
                "leader": result.leader,
                "placement": result.placement,
                "victory_points": result.victory_points,
                "league_points": int(total) if total == int(total) else total,
                "total": total,
                "formula": row["formula"],
                "is_winner": result.is_winner,
                "in_vp_tie": result.in_vp_tie,
                "sardaukar_count": result.sardaukar_count,
                "sardaukar_label": result.sardaukar_label,
                "alliances_held": result.alliances_held,
            }
        )
    rows.sort(key=lambda r: (r["placement"], r["result"].pk))
    return rows


def _select_counted_scores(
    per_game: list[tuple[float, GameResult, LeaguePointsBreakdown]],
    count_games: int,
) -> list[tuple[float, GameResult, LeaguePointsBreakdown]]:
    """Keep the best count_games by points; discard the rest."""
    ordered = sorted(per_game, key=lambda x: (-x[0], x[1].game.played_on, x[1].game_id))
    if count_games <= 0 or len(ordered) <= count_games:
        return ordered
    return ordered[:count_games]


def league_standings(league: League, results=None):
    """
    Aggregate standings. Only the best count_games per player count toward totals.

    Optional ``results`` avoids a duplicate query when the caller already loaded
    all league game results (e.g. stats page with a single-league filter).
    """
    from games.services.tiebreak import build_placement_cache

    config = resolve_scoring_config(league)
    count_games = config["count_games"]

    per_player_games: dict[str, list[tuple[float, GameResult, LeaguePointsBreakdown]]] = (
        defaultdict(list)
    )
    if results is None:
        results = list(
            GameResult.objects.filter(game__league=league).select_related(
                "game", "player", "game__designated_winner"
            )
        )
    else:
        results = list(results)
    placement_cache = build_placement_cache(results)
    game_ctx_by_id = build_game_scoring_context(results)

    for result in results:
        breakdown = compute_league_points_breakdown(
            result,
            league,
            placement=placement_cache.get(result.pk, 1),
            game_ctx=game_ctx_by_id.get(result.game_id),
        )
        per_player_games[result.player.name].append(
            (breakdown["total"], result, breakdown)
        )

    rows = []
    for name, all_games in per_player_games.items():
        games_played = len(all_games)
        counted = _select_counted_scores(all_games, count_games)
        games_counted = len(counted)
        games_discarded = games_played - games_counted

        score_total = round(sum(x[0] for x in all_games), 1)
        score_best_n = round(sum(x[0] for x in counted), 1)
        wins = sum(
            1
            for x in all_games
            if placement_cache.get(x[1].pk, 1) == 1
        )
        win_rate = (
            round(100 * wins / games_played, 1) if games_played else 0.0
        )
        score_average = (
            round(score_best_n / games_counted, 1) if games_counted else 0.0
        )

        rows.append(
            {
                "player_name": name,
                "league_points": score_best_n,
                "score_total": score_total,
                "score_best_n": score_best_n,
                "score_average": score_average,
                "win_rate": win_rate,
                "games": games_counted,
                "games_played": games_played,
                "games_discarded": games_discarded,
                "wins": wins,
                "count_games": count_games,
            }
        )
    rows.sort(
        key=lambda r: (-r["score_best_n"], -r["wins"], -r["win_rate"])
    )
    return rows
