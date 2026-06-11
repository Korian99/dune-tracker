"""
VP tie detection, resolution, and placement ranks for games.

Tie resolution is stored on ``GameResult.order`` (competition placement).
Unresolved players in a VP tie group have ``order=0`` until the desempate
form assigns placements.
"""

from collections import defaultdict
from typing import Any, Literal

from games.models import Game, GameResult

GroupOrder = list[int] | Literal["tie"]


def vp_tie_groups(game: Game) -> list[dict]:
    """
    All VP levels where two or more players share the same score.
    Sorted highest VP first. is_winner_group marks the top-VP cluster.
    """
    results = list(game.results.select_related("player"))
    if not results:
        return []
    by_vp: dict[int, list[GameResult]] = defaultdict(list)
    for result in results:
        by_vp[result.victory_points].append(result)
    max_vp = max(by_vp.keys())
    groups = []
    for vp in sorted(by_vp.keys(), reverse=True):
        tied = by_vp[vp]
        if len(tied) >= 2:
            groups.append(
                {
                    "vp": vp,
                    "results": tied,
                    "is_winner_group": vp == max_vp,
                    "player_names": [r.player.name for r in tied],
                }
            )
    return groups


def has_vp_ties(game: Game) -> bool:
    """True when any VP level has two or more players."""
    return bool(vp_tie_groups(game))


def has_top_vp_tie(game: Game) -> bool:
    """True when two or more players share the highest VP."""
    return len(game.max_vp_results()) > 1


def _game_max_vp(game: Game) -> int | None:
    results = list(game.results.all())
    if not results:
        return None
    return max(r.victory_points for r in results)


def _group_result_pks(group: list[GameResult]) -> set[int]:
    return {r.pk for r in group}


def _group_orders(group: list[GameResult]) -> dict[int, int]:
    return {r.pk: r.order for r in group}


def _group_has_unresolved_order(group: list[GameResult]) -> bool:
    return any(r.order < 1 for r in group)


def _orders_are_tie(orders: dict[int, int]) -> bool:
    values = list(orders.values())
    return len(values) >= 2 and len(set(values)) == 1 and values[0] >= 1


def _orders_are_full_rank(orders: dict[int, int]) -> bool:
    if any(o < 1 for o in orders.values()):
        return False
    values = sorted(orders.values())
    if len(values) != len(set(values)):
        return False
    return values[-1] - values[0] == len(values) - 1


def _orders_are_legacy_winner(orders: dict[int, int]) -> bool:
    """One player at min order, all others share the next rank."""
    if any(o < 1 for o in orders.values()):
        return False
    values = sorted(orders.values())
    min_order = values[0]
    winners = [o for o in values if o == min_order]
    if len(winners) != 1:
        return False
    rest = [o for o in values if o != min_order]
    return bool(rest) and len(set(rest)) == 1 and rest[0] == min_order + 1


def _resolutions_from_orders(group: list[GameResult]) -> GroupOrder | None:
    """Derive tie resolution from stored orders, or None if unresolved."""
    if _group_has_unresolved_order(group):
        return None
    orders = _group_orders(group)
    if _orders_are_tie(orders):
        return "tie"
    if _orders_are_full_rank(orders):
        return sorted(orders.keys(), key=lambda pk: orders[pk])
    if _orders_are_legacy_winner(orders):
        return None
    return None


def _group_is_legacy_winner(group: list[GameResult]) -> bool:
    return _orders_are_legacy_winner(_group_orders(group))


def _legacy_winner_pk(group: list[GameResult]) -> int | None:
    if not _group_is_legacy_winner(group):
        return None
    orders = _group_orders(group)
    min_order = min(orders.values())
    for pk, order in orders.items():
        if order == min_order:
            return pk
    return None


def vp_group_is_resolved(game: Game, group: dict) -> bool:
    """True when this VP tie has valid stored orders."""
    results = group["results"]
    if _group_has_unresolved_order(results):
        return False
    order = _resolutions_from_orders(results)
    if order is not None:
        return True
    return _group_is_legacy_winner(results)


def game_needs_tiebreak(game: Game) -> bool:
    """True when any VP tie group lacks a valid resolution."""
    return any(not vp_group_is_resolved(game, g) for g in vp_tie_groups(game))


def placements_for_game(game: Game) -> dict[int, int]:
    """Map GameResult pk -> competition placement (1–4) after tiebreaks."""
    results = list(game.results.all())
    if not results:
        return {}

    if game_orders_are_synced(game):
        return {r.pk: r.order for r in results}

    by_vp: dict[int, list[GameResult]] = defaultdict(list)
    for result in results:
        by_vp[result.victory_points].append(result)

    placements: dict[int, int] = {}
    rank = 1

    for vp in sorted(by_vp.keys(), reverse=True):
        group = by_vp[vp]
        if len(group) == 1:
            placements[group[0].pk] = rank
            rank += 1
            continue

        order = _resolutions_from_orders(group)
        if order == "tie":
            for result in group:
                placements[result.pk] = rank
            rank += len(group)
            continue

        if isinstance(order, list):
            for pk in order:
                placements[pk] = rank
                rank += 1
            continue

        if _group_is_legacy_winner(group):
            winner_pk = _legacy_winner_pk(group)
            if winner_pk is not None:
                placements[winner_pk] = rank
                rank += 1
                for result in group:
                    if result.pk != winner_pk:
                        placements[result.pk] = rank
                rank += 1
                continue

        for result in group:
            placements[result.pk] = rank
        rank += len(group)

    return placements


def result_placement(result: GameResult) -> int:
    if result.order >= 1 and game_orders_are_synced(result.game):
        return result.order
    return placements_for_game(result.game).get(result.pk, 1)


def sync_result_orders_for_game(game: Game) -> None:
    """Write competition placement onto each result's order field."""
    placements = placements_for_game(game)
    if not placements:
        return

    tie_group_pks: set[int] = set()
    for group in vp_tie_groups(game):
        if _group_has_unresolved_order(group["results"]):
            tie_group_pks.update(r.pk for r in group["results"])

    to_update: list[GameResult] = []
    for result in game.results.all():
        if result.pk in tie_group_pks:
            if result.order != 0:
                result.order = 0
                to_update.append(result)
            continue
        placement = placements.get(result.pk, 1)
        if result.order != placement:
            result.order = placement
            to_update.append(result)
    if to_update:
        GameResult.objects.bulk_update(to_update, ["order"])


def game_orders_are_synced(game: Game) -> bool:
    """True when every result has a valid synced competition placement."""
    results = list(game.results.all())
    if not results or any(r.order < 1 for r in results):
        return False
    return not game_needs_tiebreak(game)


def build_placement_cache(results) -> dict[int, int]:
    """Map GameResult pk -> placement; reads order when rows are synced."""
    if not results:
        return {}
    results_list = list(results) if not isinstance(results, list) else results
    if all(r.order >= 1 for r in results_list):
        by_game: dict[int, list[GameResult]] = defaultdict(list)
        for result in results_list:
            by_game[result.game_id].append(result)
        placements: dict[int, int] = {}
        for game_results in by_game.values():
            game = game_results[0].game
            if game_orders_are_synced(game):
                for result in game_results:
                    placements[result.pk] = result.order
            else:
                placements.update(placements_for_game(game))
        return placements

    by_game = defaultdict(list)
    for result in results_list:
        by_game[result.game_id].append(result)

    placements = {}
    for game_results in by_game.values():
        placements.update(placements_for_game(game_results[0].game))
    return placements


def normalize_tiebreaks_after_save(game: Game) -> None:
    """Reset unresolved tie-group orders and re-sync the rest."""
    groups = vp_tie_groups(game)
    unresolved_pks: set[int] = set()
    for group in groups:
        if not vp_group_is_resolved(game, group):
            unresolved_pks.update(r.pk for r in group["results"])

    to_update: list[GameResult] = []
    for result in game.results.all():
        if result.pk in unresolved_pks and result.order != 0:
            result.order = 0
            to_update.append(result)
    if to_update:
        GameResult.objects.bulk_update(to_update, ["order"])

    sync_result_orders_for_game(game)


def normalize_winner_after_save(game: Game) -> None:
    """Backward-compatible alias."""
    normalize_tiebreaks_after_save(game)


def _apply_group_placements(
    placements: dict[int, int],
    group: list[GameResult],
    resolution: str,
    *,
    winner_pk: int | None = None,
    order_pks: list[int] | None = None,
    start_rank: int,
) -> int:
    """Update placements dict for one VP group; return next rank."""
    group_pks = _group_result_pks(group)
    if resolution == "tie":
        for pk in group_pks:
            placements[pk] = start_rank
        return start_rank + len(group)

    if resolution == "rank":
        if not order_pks:
            raise ValueError("Indica el puesto de cada jugador en el grupo.")
        if set(order_pks) != group_pks or len(order_pks) != len(group_pks):
            raise ValueError("Cada jugador del empate debe tener un puesto distinto.")
        rank = start_rank
        for pk in order_pks:
            placements[pk] = rank
            rank += 1
        return rank

    if resolution != "winner" or winner_pk is None:
        raise ValueError(
            "Elige el puesto de cada jugador o marca «Empate (mismo puesto)»."
        )
    if winner_pk not in group_pks:
        raise ValueError("El jugador debe ser uno de los empatados en ese grupo.")

    placements[winner_pk] = start_rank
    rank = start_rank + 1
    if len(group) == 2:
        for pk in group_pks:
            if pk != winner_pk:
                placements[pk] = rank
        return rank + 1

    for pk in group_pks:
        if pk != winner_pk:
            placements[pk] = rank
    return rank + 1


def apply_tiebreak(
    game: Game,
    resolution: str,
    winner_result_id: str | None = None,
    *,
    vp: int | None = None,
    order_result_ids: list[int] | None = None,
) -> None:
    """Persist tiebreak for one VP group (defaults to top-VP cluster)."""
    groups = vp_tie_groups(game)
    if not groups:
        return
    max_vp = _game_max_vp(game)
    target_vp = vp if vp is not None else max_vp
    group = next((g for g in groups if g["vp"] == target_vp), None)
    if group is None:
        raise ValueError("No hay empate en ese nivel de PV.")

    winner_pk: int | None = None
    if resolution == "winner":
        if not winner_result_id:
            raise ValueError(
                "Elige el puesto de cada jugador o marca «Empate (mismo puesto)»."
            )
        try:
            winner_pk = int(winner_result_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Jugador no válido.") from exc

    placements = placements_for_game(game)
    by_vp: dict[int, list[GameResult]] = defaultdict(list)
    for result in game.results.all():
        by_vp[result.victory_points].append(result)

    tie_group_pks: set[int] = set()
    resolved_tie_pks: set[int] = set()
    rank = 1
    for vp_level in sorted(by_vp.keys(), reverse=True):
        vp_group = by_vp[vp_level]
        if len(vp_group) == 1:
            placements[vp_group[0].pk] = rank
            rank += 1
            continue

        tie_group_pks.update(r.pk for r in vp_group)

        if vp_level == target_vp:
            rank = _apply_group_placements(
                placements,
                vp_group,
                resolution,
                winner_pk=winner_pk,
                order_pks=order_result_ids,
                start_rank=rank,
            )
            resolved_tie_pks.update(r.pk for r in vp_group)
            continue

        stored = _resolutions_from_orders(vp_group)
        if stored == "tie":
            for result in vp_group:
                placements[result.pk] = rank
            rank += len(vp_group)
            resolved_tie_pks.update(r.pk for r in vp_group)
        elif isinstance(stored, list):
            for pk in stored:
                placements[pk] = rank
                rank += 1
            resolved_tie_pks.update(r.pk for r in vp_group)
        elif _group_is_legacy_winner(vp_group):
            wpk = _legacy_winner_pk(vp_group)
            if wpk is not None:
                placements[wpk] = rank
                rank += 1
                for result in vp_group:
                    if result.pk != wpk:
                        placements[result.pk] = rank
                rank += 1
                resolved_tie_pks.update(r.pk for r in vp_group)
            else:
                rank += len(vp_group)
        elif _group_has_unresolved_order(vp_group):
            rank += len(vp_group)
        else:
            for result in vp_group:
                placements[result.pk] = rank
            rank += len(vp_group)
            resolved_tie_pks.update(r.pk for r in vp_group)

    to_update: list[GameResult] = []
    for result in game.results.all():
        if result.pk in tie_group_pks and result.pk not in resolved_tie_pks:
            if result.order != 0:
                result.order = 0
                to_update.append(result)
            continue
        placement = placements.get(result.pk, 1)
        if result.order != placement:
            result.order = placement
            to_update.append(result)
    if to_update:
        GameResult.objects.bulk_update(to_update, ["order"])


def apply_tiebreaks_from_post(game: Game, post) -> None:
    """Apply all tiebreak groups submitted from the desempate form."""
    groups = vp_tie_groups(game)
    if not groups:
        return

    errors: list[str] = []
    for group in groups:
        vp = group["vp"]
        resolution = (post.get(f"tiebreak_{vp}_resolution") or "").strip()
        winner_id = (post.get(f"tiebreak_{vp}_winner") or "").strip() or None
        if not resolution:
            label = "ganador" if group["is_winner_group"] else f"{vp} PV"
            errors.append(f"Resuelve el empate de {label}.")
            continue
        try:
            if resolution == "rank":
                ranks: dict[int, int] = {}
                for result in group["results"]:
                    raw_rank = (post.get(f"tiebreak_{vp}_rank_{result.pk}") or "").strip()
                    if not raw_rank:
                        raise ValueError(
                            f"Asigna un puesto a cada jugador en el empate de {vp} PV."
                        )
                    try:
                        ranks[result.pk] = int(raw_rank)
                    except ValueError as exc:
                        raise ValueError("Puesto no válido.") from exc
                expected = set(range(1, len(group["results"]) + 1))
                if set(ranks.values()) != expected:
                    raise ValueError(
                        f"Los puestos en {vp} PV deben ser del 1º al "
                        f"{len(group['results'])}º sin repetir."
                    )
                order = sorted(ranks.keys(), key=lambda pk: ranks[pk])
                apply_tiebreak(
                    game, "rank", order_result_ids=order, vp=vp
                )
            else:
                apply_tiebreak(game, resolution, winner_id, vp=vp)
            game.refresh_from_db()
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise ValueError(" ".join(errors))

    sync_result_orders_for_game(game)


def selected_tiebreak_for_group(game: Game, group: dict) -> dict:
    """UI state for one tie group."""
    results = group["results"]

    order = _resolutions_from_orders(results)
    if order == "tie":
        return {"resolution": "tie", "winner_pk": None, "ranks": {}}

    if isinstance(order, list):
        ranks = {pk: index + 1 for index, pk in enumerate(order)}
        return {"resolution": "rank", "winner_pk": order[0], "ranks": ranks}

    if _group_is_legacy_winner(results):
        winner_pk = _legacy_winner_pk(results)
        ranks = {}
        if winner_pk is not None:
            ranks[winner_pk] = 1
            next_rank = 2
            for result in results:
                if result.pk != winner_pk:
                    ranks[result.pk] = next_rank
        return {
            "resolution": "rank" if len(results) > 2 else "winner",
            "winner_pk": winner_pk,
            "ranks": ranks,
        }

    return {"resolution": "", "winner_pk": None, "ranks": {}}
