"""
Aggregate player and leader statistics for filtered game sets.
"""

from collections import defaultdict

from django.db.models import Avg, Count, Q

from games.models import Game, GameResult, League

from .scoring import league_standings


def parse_stats_filter(request) -> tuple[list[str], bool]:
    """Return (league_slugs, include_casual) from GET params."""
    league_slugs = [s for s in request.GET.getlist("leagues") if s.strip()]
    include_casual = request.GET.get("casual") == "1"
    return league_slugs, include_casual


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
    return GameResult.objects.filter(game__in=games_qs).select_related(
        "game", "player", "game__league"
    )


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


def _count_wins(game_results) -> int:
    """Games finished 1st (matches placement_1 column; includes shared 1st on ties)."""
    return sum(1 for r in game_results if r.placement == 1)


def _placement_counts_for_results(results) -> dict[str, dict[int, int]]:
    """Per player name: how many finishes at each placement (1–4)."""
    by_player: dict[str, dict[int, int]] = defaultdict(_empty_placement_counts)
    for result in results:
        placement = result.placement
        if 1 <= placement <= 4:
            by_player[result.player.name][placement] += 1
    return dict(by_player)


def _placement_counts_for_leaders(results) -> dict[str, dict[int, int]]:
    """Per leader name: how many finishes at each placement (1–4) when that leader was played."""
    by_leader: dict[str, dict[int, int]] = defaultdict(_empty_placement_counts)
    for result in results:
        leader = (result.leader or "").strip()
        if not leader:
            continue
        placement = result.placement
        if 1 <= placement <= 4:
            by_leader[leader][placement] += 1
    return dict(by_leader)


def _attach_placement_counts(rows: list[dict], counts_by_name: dict[str, dict[int, int]]):
    """Add placement_1 … placement_4 to rows keyed by name or player_name."""
    for row in rows:
        key = row.get("name") or row.get("player_name")
        counts = counts_by_name.get(key, _empty_placement_counts())
        for place in (1, 2, 3, 4):
            row[f"placement_{place}"] = counts[place]


def aggregate_player_stats(results) -> list[dict]:
    """Player leaderboard for a flat result set (no league best-N rules)."""
    counts_by_name = _placement_counts_for_results(results)
    by_player: dict[str, list] = defaultdict(list)
    for result in results:
        by_player[result.player.name].append(result)

    rows = []
    for name, game_results in by_player.items():
        games_played = len(game_results)
        wins = _count_wins(game_results)
        vp_sum = sum(r.victory_points for r in game_results)
        placement_sum = sum(r.placement for r in game_results)
        avg_placement = placement_sum / games_played if games_played else 0
        counts = counts_by_name.get(name, _empty_placement_counts())
        rows.append(
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
    rows.sort(key=lambda r: (-r["wins"], -r["win_rate"], -r["avg_vp"]))
    return rows


def aggregate_leader_stats(results) -> list[dict]:
    """Per-leader: times played, wins, win rate, average placement, average VP."""
    counts_by_leader = _placement_counts_for_leaders(results)
    by_leader: dict[str, list] = defaultdict(list)
    for result in results:
        leader = (result.leader or "").strip()
        if leader:
            by_leader[leader].append(result)

    rows = []
    for leader, game_results in by_leader.items():
        times = len(game_results)
        wins = _count_wins(game_results)
        vp_sum = sum(r.victory_points for r in game_results)
        placement_sum = sum(r.placement for r in game_results)
        avg_placement = placement_sum / times if times else 0
        counts = counts_by_leader.get(leader, _empty_placement_counts())
        rows.append(
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
    rows.sort(key=lambda r: (-r["times_played"], -r["win_rate"], -r["avg_placement"]))
    return rows


def stats_for_filter(league_slugs: list[str], include_casual: bool):
    """
    Build player rows, leader rows, summary, and optional single-league standings.
    """
    games_qs = games_for_filter(league_slugs, include_casual)
    results = results_for_games(games_qs)
    scope_label = filter_scope_label(league_slugs, include_casual)

    summary = games_qs.aggregate(
        total=Count("id"),
        with_bloodlines=Count("id", filter=Q(bloodlines=True)),
        avg_rounds=Avg("rounds"),
        avg_duration=Avg("duration_minutes"),
    )

    league_standings_rows = None
    count_games = None
    single_league = None

    placement_counts_by_name = _placement_counts_for_results(results)

    if len(league_slugs) == 1 and not include_casual:
        single_league = League.objects.filter(slug=league_slugs[0]).first()
        if single_league:
            from .scoring import resolve_scoring_config

            league_standings_rows = league_standings(single_league)
            count_games = resolve_scoring_config(single_league)["count_games"]
            _attach_placement_counts(league_standings_rows, placement_counts_by_name)
            player_rows = league_standings_rows
        else:
            player_rows = aggregate_player_stats(results)
    else:
        player_rows = aggregate_player_stats(results)

    leader_rows = aggregate_leader_stats(results)

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
    }
