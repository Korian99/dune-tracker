"""
League hitos (highscores): definitions, defaults, and current record holders.
"""

from typing import Any, TypedDict

from .models import GameResult, League, LeagueHito
from .scoring import compute_league_points


class HitoHolderRow(TypedDict):
    player_name: str
    game_id: int
    played_on: str
    victory_points: int
    league_points: float


class HitoSnapshot(TypedDict):
    hito: LeagueHito
    value: float | int | None
    value_label: str
    holders: list[HitoHolderRow]
    empty: bool


DEFAULT_LEAGUE_HITOS: tuple[dict[str, Any], ...] = (
    {
        "slug": "highscore",
        "name": "Highscore",
        "description": "Mayor puntuación de liga en una sola partida.",
        "metric": LeagueHito.Metric.MAX_LEAGUE_POINTS,
        "order": 0,
    },
    {
        "slug": "powerscore",
        "name": "Powerscore",
        "description": "Más puntos de victoria (PV) en una sola partida.",
        "metric": LeagueHito.Metric.MAX_VICTORY_POINTS,
        "order": 1,
    },
    {
        "slug": "lowscore",
        "name": "Lowscore",
        "description": "Menor puntuación de liga en una sola partida.",
        "metric": LeagueHito.Metric.MIN_LEAGUE_POINTS,
        "order": 2,
    },
)


def ensure_default_hitos(league: League) -> list[LeagueHito]:
    """Create the three built-in hitos for a league if missing."""
    created: list[LeagueHito] = []
    for spec in DEFAULT_LEAGUE_HITOS:
        hito, was_created = LeagueHito.objects.get_or_create(
            league=league,
            slug=spec["slug"],
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "metric": spec["metric"],
                "order": spec["order"],
                "is_builtin": True,
                "is_active": True,
            },
        )
        if was_created:
            created.append(hito)
    return created


def _metric_value(result: GameResult, league: League, metric: str) -> float:
    if metric == LeagueHito.Metric.MAX_VICTORY_POINTS:
        return float(result.victory_points)
    return compute_league_points(result, league)


def _format_value(value: float, metric: str) -> str:
    if metric == LeagueHito.Metric.MAX_VICTORY_POINTS:
        return f"{int(value)} PV"
    if value == int(value):
        return str(int(value))
    return str(value)


def snapshot_for_hito(league: League, hito: LeagueHito) -> HitoSnapshot:
    """Current record holder(s) for one hito."""
    results = list(
        GameResult.objects.filter(game__league=league)
        .select_related("player", "game")
        .order_by("game__played_on", "game_id")
    )
    if not results:
        return {
            "hito": hito,
            "value": None,
            "value_label": "—",
            "holders": [],
            "empty": True,
        }

    scored = [(_metric_value(r, league, hito.metric), r) for r in results]
    if hito.metric == LeagueHito.Metric.MIN_LEAGUE_POINTS:
        target = min(v for v, _ in scored)
    else:
        target = max(v for v, _ in scored)

    holders: list[HitoHolderRow] = []
    for value, result in scored:
        if value != target:
            continue
        lp = compute_league_points(result, league)
        holders.append(
            {
                "player_name": result.player.name,
                "game_id": result.game_id,
                "played_on": result.game.played_on.isoformat(),
                "victory_points": result.victory_points,
                "league_points": lp,
            }
        )

    return {
        "hito": hito,
        "value": target,
        "value_label": _format_value(target, hito.metric),
        "holders": holders,
        "empty": False,
    }


def league_hito_snapshots(league: League) -> list[HitoSnapshot]:
    """Active hitos with current holders, ordered for display."""
    ensure_default_hitos(league)
    hitos = league.hitos.filter(is_active=True).order_by("order", "slug")
    return [snapshot_for_hito(league, hito) for hito in hitos]
