"""
Aggregate player and leader statistics for filtered game sets.
"""

from collections import defaultdict

from django.db.models import Avg, Count, Q

from games.models import Game, GameResult, League, Player

from .scoring import league_standings


def parse_stats_filter(request) -> tuple[list[str], bool, list[str]]:
    """Return (league_slugs, include_casual, player_slugs) from GET params."""
    league_slugs = [s for s in request.GET.getlist("leagues") if s.strip()]
    include_casual = request.GET.get("casual") == "1"
    player_slugs = [s for s in request.GET.getlist("players") if s.strip()]
    return league_slugs, include_casual, player_slugs


def games_for_filter(league_slugs: list[str], include_casual: bool):
    """Games queryset matching league / casual filter. Empty slugs + no casual = all."""
    if not league_slugs and not include_casual:
        return Game.objects.all()
    q = Q()
    if league_slugs:
        q |= Q(league__slug__in=league_slugs)
    if include_casual:
        q |= Q(league__isnull=True)
    return Game.objects.filter(q)


def filter_scope_label(league_slugs: list[str], include_casual: bool) -> str:
    if not league_slugs and not include_casual:
        return "Todas las partidas"
    parts = []
    if league_slugs:
        names = list(
            League.objects.filter(slug__in=league_slugs)
            .order_by("name")
            .values_list("name", flat=True)
        )
        parts.extend(names)
    if include_casual:
        parts.append("Partidas sin liga")
    return " · ".join(parts)


def results_for_games(games_qs):
    """Load result rows for stats; placement comes from synced order field."""
    return GameResult.objects.filter(game__in=games_qs).select_related(
        "game", "player", "game__league", "game__designated_winner"
    )


def players_from_results(results_list: list[GameResult]):
    """Distinct players in result order by name."""
    by_id: dict[int, Player] = {}
    for result in results_list:
        by_id[result.player_id] = result.player
    return sorted(by_id.values(), key=lambda p: p.name)


def leader_filter_label(
    player_slugs: list[str],
    filter_players: list[Player] | None = None,
) -> str | None:
    """Spanish label for leader-stats player filter, or None if unset."""
    if not player_slugs:
        return None
    slug_set = set(player_slugs)
    if filter_players:
        names = [p.name for p in filter_players if p.slug in slug_set]
        if names:
            return " · ".join(names)
    names = list(
        Player.objects.filter(slug__in=player_slugs).order_by("name").values_list("name", flat=True)
    )
    if not names:
        return None
    return " · ".join(names)


def _format_placement(avg: float) -> str:
    if avg <= 1.4:
        return "1.º"
    if avg <= 2.4:
        return "2.º"
    if avg <= 3.4:
        return "3.º"
    if avg <= 4.4:
        return "4.º"
    return f"{avg:.1f}.º"


def _empty_placement_counts() -> dict[int, int]:
    return {1: 0, 2: 0, 3: 0, 4: 0}


def _placement_cache(results_list: list[GameResult]) -> dict[int, int]:
    """Fast path: order field is placement after sync_result_orders_for_game."""
    if not results_list:
        return {}
    if all(r.order >= 1 for r in results_list):
        return {r.pk: r.order for r in results_list}
    from games.services.tiebreak import build_placement_cache

    return build_placement_cache(results_list)


def _attach_placement_counts(rows: list[dict], counts_by_name: dict[str, dict[int, int]]):
    """Add placement_1 … placement_4 to rows keyed by name or player_name."""
    for row in rows:
        key = row.get("name") or row.get("player_name")
        counts = counts_by_name.get(key, _empty_placement_counts())
        for place in (1, 2, 3, 4):
            row[f"placement_{place}"] = counts[place]


def _aggregate_player_and_leader_stats(
    results_list: list[GameResult],
    placement_cache: dict[int, int],
    *,
    leader_player_slugs: set[str] | None = None,
) -> tuple[list[dict], list[dict], dict[str, dict[int, int]]]:
    """
    Single pass: player rows, leader rows, and per-player placement counts.
    """
    by_player: dict[str, list[tuple[GameResult, int]]] = defaultdict(list)
    by_leader: dict[str, list[tuple[GameResult, int]]] = defaultdict(list)
    counts_by_name: dict[str, dict[int, int]] = defaultdict(_empty_placement_counts)
    counts_by_leader: dict[str, dict[int, int]] = defaultdict(_empty_placement_counts)

    for result in results_list:
        placement = placement_cache.get(result.pk, 1)
        name = result.player.name
        by_player[name].append((result, placement))
        if 1 <= placement <= 4:
            counts_by_name[name][placement] += 1

        leader = (result.leader or "").strip()
        if not leader:
            continue
        if leader_player_slugs is not None and result.player.slug not in leader_player_slugs:
            continue
        by_leader[leader].append((result, placement))
        if 1 <= placement <= 4:
            counts_by_leader[leader][placement] += 1

    player_rows = []
    for name, entries in by_player.items():
        games_played = len(entries)
        wins = sum(1 for _, place in entries if place == 1)
        vp_sum = sum(r.victory_points for r, _ in entries)
        placement_sum = sum(place for _, place in entries)
        avg_placement = placement_sum / games_played if games_played else 0
        counts = counts_by_name.get(name, _empty_placement_counts())
        player_rows.append(
            {
                "name": name,
                "games": games_played,
                "wins": wins,
                "win_rate": round(100 * wins / games_played, 1) if games_played else 0,
                "avg_vp": round(vp_sum / games_played, 1) if games_played else 0,
                "avg_placement": round(avg_placement, 1),
                "usual_placement": _format_placement(avg_placement),
                "placement_1": counts[1],
                "placement_2": counts[2],
                "placement_3": counts[3],
                "placement_4": counts[4],
            }
        )
    player_rows.sort(key=lambda r: (-r["wins"], -r["win_rate"], -r["avg_vp"]))

    leader_rows = []
    for leader, entries in by_leader.items():
        times = len(entries)
        wins = sum(1 for _, place in entries if place == 1)
        vp_sum = sum(r.victory_points for r, _ in entries)
        placement_sum = sum(place for _, place in entries)
        avg_placement = placement_sum / times if times else 0
        counts = counts_by_leader.get(leader, _empty_placement_counts())
        leader_rows.append(
            {
                "leader": leader,
                "times_played": times,
                "wins": wins,
                "win_rate": round(100 * wins / times, 1) if times else 0,
                "avg_vp": round(vp_sum / times, 1) if times else 0,
                "avg_placement": round(avg_placement, 1),
                "usual_placement": _format_placement(avg_placement),
                "placement_1": counts[1],
                "placement_2": counts[2],
                "placement_3": counts[3],
                "placement_4": counts[4],
            }
        )
    leader_rows.sort(key=lambda r: (-r["times_played"], -r["win_rate"], -r["avg_placement"]))

    return player_rows, leader_rows, dict(counts_by_name)


def aggregate_player_stats(results, *, placement_cache: dict[int, int] | None = None) -> list[dict]:
    """Player leaderboard for a flat result set (no league best-N rules)."""
    results_list = list(results) if not isinstance(results, list) else results
    if placement_cache is None:
        placement_cache = _placement_cache(results_list)
    player_rows, _, _ = _aggregate_player_and_leader_stats(results_list, placement_cache)
    return player_rows


def aggregate_leader_stats(results, *, placement_cache: dict[int, int] | None = None) -> list[dict]:
    """Per-leader: times played, wins, win rate, average placement, average VP."""
    results_list = list(results) if not isinstance(results, list) else results
    if placement_cache is None:
        placement_cache = _placement_cache(results_list)
    _, leader_rows, _ = _aggregate_player_and_leader_stats(results_list, placement_cache)
    return leader_rows


def stats_for_filter(
    league_slugs: list[str],
    include_casual: bool,
    *,
    player_slugs: list[str] | None = None,
):
    """
    Build player rows, leader rows, summary, and optional single-league standings.

    When player_slugs is set, leader_rows only include results for those players;
    player_rows and summary still use the full game filter.
    """
    player_slugs = player_slugs or []
    games_qs = games_for_filter(league_slugs, include_casual)
    results_list = list(results_for_games(games_qs))
    placement_cache = _placement_cache(results_list)

    scope_label = filter_scope_label(league_slugs, include_casual)
    filter_players = players_from_results(results_list)

    summary = games_qs.aggregate(
        total=Count("id"),
        with_bloodlines=Count("id", filter=Q(bloodlines=True)),
        avg_rounds=Avg("rounds"),
        avg_duration=Avg("duration_minutes"),
    )

    league_standings_rows = None
    count_games = None
    single_league = None
    leader_slug_set = set(player_slugs) if player_slugs else None

    use_single_league = len(league_slugs) == 1 and not include_casual
    if use_single_league:
        single_league = League.objects.filter(slug=league_slugs[0]).first()

    if use_single_league and single_league:
        from .scoring import resolve_scoring_config

        _, leader_rows, counts_by_name = _aggregate_player_and_leader_stats(
            results_list,
            placement_cache,
            leader_player_slugs=leader_slug_set,
        )
        league_standings_rows = league_standings(single_league, results=results_list)
        count_games = resolve_scoring_config(single_league)["count_games"]
        _attach_placement_counts(league_standings_rows, counts_by_name)
        player_rows = league_standings_rows
    else:
        player_rows, leader_rows, _ = _aggregate_player_and_leader_stats(
            results_list,
            placement_cache,
            leader_player_slugs=leader_slug_set,
        )

    return {
        "scope_label": scope_label,
        "summary": summary,
        "player_rows": player_rows,
        "leader_rows": leader_rows,
        "league_standings": league_standings_rows,
        "count_games": count_games,
        "single_league": single_league,
        "use_league_scoring": league_standings_rows is not None,
        "league_slugs": league_slugs,
        "include_casual": include_casual,
        "player_slugs": player_slugs,
        "filter_players": filter_players,
        "leader_filter_label": leader_filter_label(player_slugs, filter_players),
    }
