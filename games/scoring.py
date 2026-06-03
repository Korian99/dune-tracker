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

from collections import defaultdict
from typing import Any, TypedDict

from .defaults import DEFAULT_LEAGUE_SCORING_NOTES, default_league_scoring_config
from .models import GameResult, League

DEFAULT_SCORING_NOTES = DEFAULT_LEAGUE_SCORING_NOTES


def default_scoring_config() -> dict[str, Any]:
    """Alias for migrations/tests; placement keys normalized on read."""
    raw = default_league_scoring_config()
    return {
        **raw,
        "placement_points": {int(k): int(v) for k, v in raw["placement_points"].items()},
    }


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
    thresholds = []
    if cleaned.get("vp_bonus_10"):
        thresholds.append(10)
    if cleaned.get("vp_bonus_12"):
        thresholds.append(12)
    if cleaned.get("vp_bonus_15"):
        thresholds.append(15)
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
    thresholds = set(cfg.get("vp_thresholds", []))
    return {
        "count_games": cfg["count_games"],
        "points_1st": pp.get(1, 5),
        "points_2nd": pp.get(2, 3),
        "points_3rd": pp.get(3, 2),
        "points_4th": pp.get(4, 1),
        "early_win_max_round": cfg["early_win_max_round"],
        "vp_bonus_10": 10 in thresholds,
        "vp_bonus_12": 12 in thresholds,
        "vp_bonus_15": 15 in thresholds,
    }


class LeaguePointsBreakdown(TypedDict):
    placement: int
    placement_points: int
    early_win: int
    vp_threshold_bonuses: int
    total: float


def _config_system(config: dict[str, Any]) -> str:
    return config.get("system") or "standard"


def _has_highest_vp(result: GameResult) -> bool:
    """True if this result ties for the game maximum VP (not pk tie-break)."""
    max_vp = (
        result.game.results.order_by("-victory_points")
        .values_list("victory_points", flat=True)
        .first()
    )
    return max_vp is not None and result.victory_points == max_vp


def _vp_threshold_bonuses(vp: int, thresholds: list[int]) -> int:
    return sum(1 for t in thresholds if vp >= t)


def compute_league_points_breakdown(
    result: GameResult, league: League
) -> LeaguePointsBreakdown:
    """
    Per-game league points with components.

    Ties (placement): GameResult.placement — competition ranking by VP.
    Ties (early-win): all players at max VP qualify (not is_winner pk tie-break).
    """
    config = resolve_scoring_config(league)

    if _config_system(config) == "victory_points":
        vp = float(result.victory_points)
        return LeaguePointsBreakdown(
            placement=result.placement,
            placement_points=0,
            early_win=0,
            vp_threshold_bonuses=0,
            total=vp,
        )

    placement = result.placement
    placement_pts = config["placement_points"].get(placement, 0)

    early_win = 0
    max_round = config["early_win_max_round"]
    if max_round > 0 and _has_highest_vp(result):
        rounds = result.game.rounds
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


def game_score_summary(game, league: League) -> list[dict[str, Any]]:
    """Per-player league scoring for one game, sorted by placement."""
    rows = []
    results = list(game.results.select_related("player"))
    results.sort(key=lambda r: (r.placement, r.pk))
    for result in results:
        breakdown = compute_league_points_breakdown(result, league)
        total = breakdown["total"]
        rows.append(
            {
                "player_name": result.player.name,
                "placement": result.placement,
                "victory_points": result.victory_points,
                "league_points": int(total) if total == int(total) else total,
                "formula": breakdown_display(breakdown),
                "is_winner": result.is_winner,
            }
        )
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


def league_standings(league: League):
    """
    Aggregate standings. Only the best count_games per player count toward totals.
    """
    config = resolve_scoring_config(league)
    count_games = config["count_games"]

    per_player_games: dict[str, list[tuple[float, GameResult, LeaguePointsBreakdown]]] = (
        defaultdict(list)
    )
    results = GameResult.objects.filter(game__league=league).select_related(
        "game", "player"
    )

    for result in results:
        breakdown = compute_league_points_breakdown(result, league)
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
        wins = sum(1 for x in all_games if x[1].is_winner)
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
