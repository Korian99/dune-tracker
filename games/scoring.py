"""
League scoring for Dune Tracker.

Default system (empty scoring_config or system omitted / "standard"):
  - Placement by victory_points (competition ranking; see tie notes below).
  - Placement points: 1st=5, 2nd=3, 3rd=2, 4th=1, 5th+=0.
  - +1 early-win bonus if the player tied for highest VP and game.rounds is 1–6.
  - +1 each if final VP >= 10, >= 12, >= 15 (stacking).

Alternate: scoring_config {"system": "victory_points"} — league points = VP.
"""

from collections import defaultdict
from typing import TypedDict

from .models import GameResult, League

# Spanish default for new leagues (user-facing; editable per league).
DEFAULT_SCORING_NOTES = """\
Puntos por partida:
• Puesto: 1.º = 5, 2.º = 3, 3.º = 2, 4.º = 1 (5.º o peor = 0).
• +1 si ganas antes de la ronda 7 (rondas 1–6 registradas).
• +1 si terminas con 10+ PV, +1 con 12+ PV, +1 con 15+ PV (se suman).
"""

PLACEMENT_POINTS = {1: 5, 2: 3, 3: 2, 4: 1}


class LeaguePointsBreakdown(TypedDict):
    placement: int
    placement_points: int
    early_win: int
    vp_ge_10: int
    vp_ge_12: int
    vp_ge_15: int
    total: float


def _config_system(league: League) -> str:
    config = league.scoring_config or {}
    return config.get("system") or "standard"


def _has_highest_vp(result: GameResult) -> bool:
    """True if this result ties for the game maximum VP (not pk tie-break)."""
    max_vp = (
        result.game.results.order_by("-victory_points")
        .values_list("victory_points", flat=True)
        .first()
    )
    return max_vp is not None and result.victory_points == max_vp


def compute_league_points_breakdown(
    result: GameResult, league: League
) -> LeaguePointsBreakdown:
    """
    Per-game league points with components.

    Ties (placement): uses GameResult.placement — competition ranking by VP
    (e.g. two players at 10 VP both rank 1st; next player is 3rd, not 2nd).

    Ties (early-win bonus): every player at the game's maximum VP qualifies;
    does not use GameResult.is_winner (which breaks ties by lowest id).
    """
    if _config_system(league) == "victory_points":
        vp = float(result.victory_points)
        return LeaguePointsBreakdown(
            placement=result.placement,
            placement_points=0,
            early_win=0,
            vp_ge_10=0,
            vp_ge_12=0,
            vp_ge_15=0,
            total=vp,
        )

    placement = result.placement
    placement_pts = PLACEMENT_POINTS.get(placement, 0)

    early_win = 0
    if _has_highest_vp(result):
        rounds = result.game.rounds
        if rounds is not None and 1 <= rounds <= 6:
            early_win = 1

    vp = result.victory_points
    vp_ge_10 = 1 if vp >= 10 else 0
    vp_ge_12 = 1 if vp >= 12 else 0
    vp_ge_15 = 1 if vp >= 15 else 0

    total = float(
        placement_pts + early_win + vp_ge_10 + vp_ge_12 + vp_ge_15
    )
    return LeaguePointsBreakdown(
        placement=placement,
        placement_points=placement_pts,
        early_win=early_win,
        vp_ge_10=vp_ge_10,
        vp_ge_12=vp_ge_12,
        vp_ge_15=vp_ge_15,
        total=total,
    )


def compute_league_points(result: GameResult, league: League) -> float:
    """Points earned by one player in one game under league rules."""
    return compute_league_points_breakdown(result, league)["total"]


def breakdown_display(breakdown: LeaguePointsBreakdown) -> str:
    """Compact formula for templates, e.g. 5+1+1+1=8."""
    parts = [str(breakdown["placement_points"])]
    if breakdown["early_win"]:
        parts.append("1")
    if breakdown["vp_ge_10"]:
        parts.append("1")
    if breakdown["vp_ge_12"]:
        parts.append("1")
    if breakdown["vp_ge_15"]:
        parts.append("1")
    total = breakdown["total"]
    total_str = str(int(total)) if total == int(total) else str(total)
    return "+".join(parts) + f"={total_str}"


def league_standings(league: League):
    """
    Aggregate standings for a league. Returns list of dicts sorted by points.

    Each row includes league_points, games, wins, avg_vp, and bonus totals
    (early_win_count, vp_bonus_count) for optional display.
    """
    totals = defaultdict(
        lambda: {
            "points": 0.0,
            "games": 0,
            "wins": 0,
            "vp_sum": 0,
            "early_wins": 0,
            "vp_bonuses": 0,
        }
    )
    results = GameResult.objects.filter(game__league=league).select_related("game")

    for result in results:
        name = result.player_name
        breakdown = compute_league_points_breakdown(result, league)
        pts = breakdown["total"]
        totals[name]["points"] += pts
        totals[name]["games"] += 1
        totals[name]["vp_sum"] += result.victory_points
        if result.is_winner:
            totals[name]["wins"] += 1
        totals[name]["early_wins"] += breakdown["early_win"]
        totals[name]["vp_bonuses"] += (
            breakdown["vp_ge_10"]
            + breakdown["vp_ge_12"]
            + breakdown["vp_ge_15"]
        )

    rows = []
    for name, data in totals.items():
        games = data["games"]
        rows.append(
            {
                "player_name": name,
                "league_points": round(data["points"], 1),
                "games": games,
                "wins": data["wins"],
                "avg_vp": round(data["vp_sum"] / games, 1) if games else 0,
                "early_wins": data["early_wins"],
                "vp_bonuses": data["vp_bonuses"],
            }
        )
    rows.sort(key=lambda r: (-r["league_points"], -r["wins"], -r["avg_vp"]))
    return rows
