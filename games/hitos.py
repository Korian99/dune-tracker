"""
League hitos: Highscore/Lowscore from max/min VP; Powerscore edited manually.
"""

from typing import Any, TypedDict

from .models import GameResult, League, LeagueHito


class HitoHolderRow(TypedDict, total=False):
    player_name: str
    game_id: int | None
    played_on: str
    victory_points: int


class HitoSnapshot(TypedDict):
    hito: LeagueHito
    value: int | None
    value_label: str
    holders: list[HitoHolderRow]
    empty: bool
    is_manual: bool


DEFAULT_LEAGUE_HITOS: tuple[dict[str, Any], ...] = (
    {
        "slug": "highscore",
        "name": "Highscore",
        "description": "Mayor PV en una partida (automático).",
        "metric": LeagueHito.Metric.AUTO_MAX_VP,
        "order": 0,
    },
    {
        "slug": "powerscore",
        "name": "Powerscore",
        "description": "Récord de la liga; edítalo al guardar la liga.",
        "metric": LeagueHito.Metric.MANUAL,
        "order": 1,
    },
    {
        "slug": "lowscore",
        "name": "Lowscore",
        "description": "Menor PV en una partida (automático).",
        "metric": LeagueHito.Metric.AUTO_MIN_VP,
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


def powerscore_hito(league: League) -> LeagueHito | None:
    ensure_default_hitos(league)
    return league.hitos.filter(slug="powerscore").first()


def _auto_vp_snapshot(league: League, hito: LeagueHito, pick_max: bool) -> HitoSnapshot:
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
            "is_manual": False,
        }

    target = (
        max(r.victory_points for r in results)
        if pick_max
        else min(r.victory_points for r in results)
    )
    holders: list[HitoHolderRow] = []
    for result in results:
        if result.victory_points != target:
            continue
        holders.append(
            {
                "player_name": result.player.name,
                "game_id": result.game_id,
                "played_on": result.game.played_on.isoformat(),
                "victory_points": result.victory_points,
            }
        )

    return {
        "hito": hito,
        "value": target,
        "value_label": f"{target} PV",
        "holders": holders,
        "empty": False,
        "is_manual": False,
    }


def _manual_holder_names(hito: LeagueHito) -> list[str]:
    """Player names for manual hito holders (M2M preferred, legacy FK fallback)."""
    names = list(hito.manual_players.order_by("name").values_list("name", flat=True))
    if names:
        return names
    if hito.manual_player_id:
        return [hito.manual_player.name]
    return []


def _manual_snapshot(hito: LeagueHito) -> HitoSnapshot:
    holder_names = _manual_holder_names(hito)
    has_content = bool(hito.manual_value.strip()) or bool(holder_names)
    holders: list[HitoHolderRow] = [
        {"player_name": name} for name in holder_names
    ]

    label = hito.manual_value.strip() or "—"
    return {
        "hito": hito,
        "value": None,
        "value_label": label,
        "holders": holders,
        "empty": not has_content,
        "is_manual": True,
    }


def snapshot_for_hito(league: League, hito: LeagueHito) -> HitoSnapshot:
    if hito.metric == LeagueHito.Metric.MANUAL:
        return _manual_snapshot(hito)
    if hito.metric == LeagueHito.Metric.AUTO_MIN_VP:
        return _auto_vp_snapshot(league, hito, pick_max=False)
    return _auto_vp_snapshot(league, hito, pick_max=True)


def league_hito_snapshots(league: League) -> list[HitoSnapshot]:
    ensure_default_hitos(league)
    hitos = (
        league.hitos.filter(is_active=True)
        .select_related("manual_player")
        .prefetch_related("manual_players")
    )
    hitos = hitos.order_by("order", "slug")
    return [snapshot_for_hito(league, hito) for hito in hitos]
