"""
VP tie detection, resolution, and placement ranks for games.

placement_tiebreaks JSON per VP key (string):
  - "tie" — all players in the group share the same competition rank
  - int or numeric string — legacy: one winner, others share next rank
  - [pk, pk, ...] — full order within the group (1st → last among tied VP)
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


def _parse_stored_order(raw: Any, group_pks: set[int]) -> GroupOrder | None:
    """Return ordered pks, 'tie', or None (unresolved / legacy winner int)."""
    if raw is None:
        return None
    if raw == "tie":
        return "tie"
    if isinstance(raw, list):
        try:
            pks = [int(x) for x in raw]
        except (TypeError, ValueError):
            return None
        if len(pks) == len(group_pks) and set(pks) == group_pks:
            return pks
        return None
    try:
        winner_pk = int(raw)
    except (TypeError, ValueError):
        return None
    if winner_pk not in group_pks:
        return None
    return None  # legacy int handled separately


def _group_placement_order(
    game: Game, vp: int, group: list[GameResult]
) -> GroupOrder | None:
    """
    Return full pk order (best → worst within group), 'tie', or None if unresolved.
    Legacy winner-only: None (placements_for_game applies winner + shared rank).
    """
    group_pks = _group_result_pks(group)
    max_vp = _game_max_vp(game)

    tiebreaks = game.placement_tiebreaks or {}
    raw = tiebreaks.get(str(vp))

    if vp == max_vp:
        if game.tied_game:
            return "tie"
        parsed = _parse_stored_order(raw, group_pks)
        if parsed is not None:
            return parsed
        if game.designated_winner_id and game.designated_winner_id in group_pks:
            return None  # legacy winner-only
        return None

    parsed = _parse_stored_order(raw, group_pks)
    if parsed is not None:
        return parsed
    return None


def _group_is_legacy_winner(game: Game, vp: int, group: list[GameResult]) -> bool:
    """True when only a single winner is stored (others share next rank)."""
    group_pks = _group_result_pks(group)
    max_vp = _game_max_vp(game)
    tiebreaks = game.placement_tiebreaks or {}
    raw = tiebreaks.get(str(vp))

    if vp == max_vp:
        if game.tied_game:
            return False
        if isinstance(raw, list):
            return False
        if raw == "tie":
            return False
        return bool(
            game.designated_winner_id
            and game.designated_winner_id in group_pks
            and not isinstance(raw, list)
        )

    if isinstance(raw, list) or raw == "tie" or raw is None:
        return False
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return False
    return pk in group_pks


def _legacy_winner_pk(game: Game, vp: int, group: list[GameResult]) -> int | None:
    group_pks = _group_result_pks(group)
    max_vp = _game_max_vp(game)
    if vp == max_vp and game.designated_winner_id in group_pks:
        return game.designated_winner_id
    raw = (game.placement_tiebreaks or {}).get(str(vp))
    if raw is None or raw == "tie" or isinstance(raw, list):
        return None
    try:
        pk = int(raw)
    except (TypeError, ValueError):
        return None
    return pk if pk in group_pks else None


def vp_group_is_resolved(game: Game, group: dict) -> bool:
    """True when this VP tie has a stored resolution."""
    vp = group["vp"]
    results = group["results"]
    order = _group_placement_order(game, vp, results)
    if order is not None:
        return True
    if _group_is_legacy_winner(game, vp, results):
        return True
    return False


def game_needs_tiebreak(game: Game) -> bool:
    """True when any VP tie group lacks a resolution."""
    return any(not vp_group_is_resolved(game, g) for g in vp_tie_groups(game))


def placements_for_game(game: Game) -> dict[int, int]:
    """Map GameResult pk -> competition placement (1–4) after tiebreaks."""
    results = list(game.results.all())
    if not results:
        return {}

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

        order = _group_placement_order(game, vp, group)
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

        if _group_is_legacy_winner(game, vp, group):
            winner_pk = _legacy_winner_pk(game, vp, group)
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
    """Write competition placement (1–4) onto each result's order field."""
    placements = placements_for_game(game)
    if not placements:
        return
    to_update: list[GameResult] = []
    for result in game.results.all():
        placement = placements.get(result.pk, 1)
        if result.order != placement:
            result.order = placement
            to_update.append(result)
    if to_update:
        GameResult.objects.bulk_update(to_update, ["order"])


def game_orders_are_synced(game: Game) -> bool:
    """True when every result row has order set to competition placement."""
    results = list(game.results.all())
    return bool(results) and all(r.order >= 1 for r in results)


def build_placement_cache(results) -> dict[int, int]:
    """Map GameResult pk -> placement; reads order when rows are synced."""
    if not results:
        return {}
    results_list = list(results) if not isinstance(results, list) else results
    if all(r.order >= 1 for r in results_list):
        return {r.pk: r.order for r in results_list}

    by_game: dict[int, list[GameResult]] = defaultdict(list)
    for result in results_list:
        by_game[result.game_id].append(result)

    placements: dict[int, int] = {}
    for game_results in by_game.values():
        if all(r.order >= 1 for r in game_results):
            for result in game_results:
                placements[result.pk] = result.order
        else:
            placements.update(placements_for_game(game_results[0].game))
    return placements


def normalize_tiebreaks_after_save(game: Game) -> None:
    """Drop tiebreak data that no longer matches saved scores."""
    groups = vp_tie_groups(game)
    group_vps = {g["vp"] for g in groups}
    max_vp = _game_max_vp(game)
    leaders = game.max_vp_results()
    leader_ids = {r.pk for r in leaders}
    update_fields: list[str] = []

    tiebreaks = dict(game.placement_tiebreaks or {})
    cleaned: dict[str, Any] = {}
    for key, raw in tiebreaks.items():
        try:
            vp = int(key)
        except (TypeError, ValueError):
            continue
        if vp not in group_vps:
            continue
        group = next(g for g in groups if g["vp"] == vp)
        group_pks = _group_result_pks(group["results"])
        if raw == "tie":
            cleaned[key] = "tie"
            continue
        if isinstance(raw, list):
            try:
                pks = [int(x) for x in raw]
            except (TypeError, ValueError):
                continue
            if set(pks) == group_pks and len(pks) == len(group_pks):
                cleaned[key] = pks
            continue
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            continue
        if pk in group_pks:
            if vp == max_vp:
                continue  # max VP uses designated_winner for legacy int
            cleaned[key] = pk

    if cleaned != tiebreaks:
        game.placement_tiebreaks = cleaned
        update_fields.append("placement_tiebreaks")

    if len(leaders) <= 1:
        if game.tied_game or game.designated_winner_id:
            game.tied_game = False
            game.designated_winner = None
            update_fields.extend(["tied_game", "designated_winner"])
    elif game.designated_winner_id and game.designated_winner_id not in leader_ids:
        game.designated_winner = None
        game.tied_game = False
        update_fields.extend(["tied_game", "designated_winner"])

    if update_fields:
        game.save(update_fields=list(dict.fromkeys(update_fields)))

    sync_result_orders_for_game(game)


def normalize_winner_after_save(game: Game) -> None:
    """Backward-compatible alias."""
    normalize_tiebreaks_after_save(game)


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

    result_ids = _group_result_pks(group["results"])
    tiebreaks = dict(game.placement_tiebreaks or {})

    if resolution == "tie":
        if target_vp == max_vp:
            game.tied_game = True
            game.designated_winner = None
            tiebreaks.pop(str(target_vp), None)
            game.placement_tiebreaks = tiebreaks
            game.save(
                update_fields=["tied_game", "designated_winner", "placement_tiebreaks"]
            )
        else:
            tiebreaks[str(target_vp)] = "tie"
            game.placement_tiebreaks = tiebreaks
            game.save(update_fields=["placement_tiebreaks"])
        sync_result_orders_for_game(game)
        return

    if resolution == "rank":
        if not order_result_ids:
            raise ValueError("Indica el puesto de cada jugador en el grupo.")
        if set(order_result_ids) != result_ids:
            raise ValueError("Cada jugador del empate debe tener un puesto distinto.")
        if len(order_result_ids) != len(result_ids):
            raise ValueError("Faltan jugadores en el orden del empate.")
        tiebreaks[str(target_vp)] = order_result_ids
        game.placement_tiebreaks = tiebreaks
        if target_vp == max_vp:
            game.tied_game = False
            game.designated_winner_id = order_result_ids[0]
            game.save(
                update_fields=[
                    "placement_tiebreaks",
                    "tied_game",
                    "designated_winner",
                ]
            )
        else:
            game.save(update_fields=["placement_tiebreaks"])
        sync_result_orders_for_game(game)
        return

    if resolution != "winner" or not winner_result_id:
        raise ValueError(
            "Elige el puesto de cada jugador o marca «Empate (mismo puesto)»."
        )

    try:
        winner_pk = int(winner_result_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Jugador no válido.") from exc

    if winner_pk not in result_ids:
        raise ValueError("El jugador debe ser uno de los empatados en ese grupo.")

    if target_vp == max_vp:
        game.tied_game = False
        game.designated_winner_id = winner_pk
        tiebreaks.pop(str(target_vp), None)
        game.placement_tiebreaks = tiebreaks
        game.save(
            update_fields=["tied_game", "designated_winner", "placement_tiebreaks"]
        )
    else:
        tiebreaks[str(target_vp)] = winner_pk
        game.placement_tiebreaks = tiebreaks
        game.save(update_fields=["placement_tiebreaks"])
    sync_result_orders_for_game(game)


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
    vp = group["vp"]
    results = group["results"]
    group_pks = _group_result_pks(results)

    order = _group_placement_order(game, vp, results)
    if order == "tie":
        return {"resolution": "tie", "winner_pk": None, "ranks": {}}

    if isinstance(order, list):
        ranks = {pk: index + 1 for index, pk in enumerate(order)}
        return {"resolution": "rank", "winner_pk": order[0], "ranks": ranks}

    if _group_is_legacy_winner(game, vp, results):
        winner_pk = _legacy_winner_pk(game, vp, results)
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
