"""
League scoring — placeholder until custom rules are defined.

Extend `compute_league_points` and `league_standings` when scoring_config
is specified in AGENTS.md / league scoring_notes.
"""

from collections import defaultdict

from .models import GameResult, League


def compute_league_points(result: GameResult, league: League) -> float:
    """
    Points earned by one player in one game under league rules.

    Default: placement-based stub (winner=3, 2nd=2, 3rd=1, else 0).
    Override when league.scoring_config is populated.
    """
    config = league.scoring_config or {}
    if config.get("system") == "victory_points":
        return float(result.victory_points)

    placement = result.placement
    table = config.get("placement_points", {1: 3, 2: 2, 3: 1})
    return float(table.get(str(placement), table.get(placement, 0)))


def league_standings(league: League):
    """
    Aggregate standings for a league. Returns list of dicts sorted by points.
    """
    totals = defaultdict(lambda: {"points": 0.0, "games": 0, "wins": 0, "vp_sum": 0})
    results = GameResult.objects.filter(game__league=league).select_related("game")

    for result in results:
        name = result.player_name
        pts = compute_league_points(result, league)
        totals[name]["points"] += pts
        totals[name]["games"] += 1
        totals[name]["vp_sum"] += result.victory_points
        if result.is_winner:
            totals[name]["wins"] += 1

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
            }
        )
    rows.sort(key=lambda r: (-r["league_points"], -r["wins"], -r["avg_vp"]))
    return rows
