"""
VP tie detection, resolution, and placement ranks for games.
"""

from collections import defaultdict
from typing import Any

from .models import Game, GameResult


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


def _vp_group_resolution(
    game: Game, vp: int, group: list[GameResult]
) -> tuple[GameResult | None, str]:
    """
    Return (winner, mode) for a tied VP cluster.
    mode is 'winner', 'tie', or 'unresolved'.
    """
    max_vp = _game_max_vp(game)
    if max_vp is None:
        return None, "unresolved"

    if vp == max_vp:
        if game.tied_game:
            return None, "tie"
        winner = game.resolved_winner()
        if winner is not None and winner in group:
            return winner, "winner"
        return None, "unresolved"

    tiebreaks = game.placement_tiebreaks or {}
    raw = tiebreaks.get(str(vp))
    if raw is None:
        return None, "unresolved"
    if raw == "tie":
        return None, "tie"
    try:
        winner_pk = int(raw)
    except (TypeError, ValueError):
        return None, "unresolved"
    winner = next((r for r in group if r.pk == winner_pk), None)
    if winner is None:
        return None, "unresolved"
    return winner, "winner"


def vp_group_is_resolved(game: Game, group: dict) -> bool:
    """True when this VP tie has a stored winner or declared tie."""
    _, mode = _vp_group_resolution(game, group["vp"], group["results"])
    return mode in ("winner", "tie")


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

        winner, mode = _vp_group_resolution(game, vp, group)
        if mode == "winner" and winner is not None:
            placements[winner.pk] = rank
            rank += 1
            losers = [r for r in group if r.pk != winner.pk]
            if losers:
                for result in losers:
                    placements[result.pk] = rank
                rank += 1
        else:
            for result in group:
                placements[result.pk] = rank
            rank += len(group)

    return placements


def result_placement(result: GameResult) -> int:
    return placements_for_game(result.game).get(result.pk, 1)


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
        if vp not in group_vps or vp == max_vp:
            continue
        group = next(g for g in groups if g["vp"] == vp)
        if raw == "tie":
            cleaned[key] = "tie"
            continue
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            continue
        if any(r.pk == pk for r in group["results"]):
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


def normalize_winner_after_save(game: Game) -> None:
    """Backward-compatible alias."""
    normalize_tiebreaks_after_save(game)


def apply_tiebreak(
    game: Game,
    resolution: str,
    winner_result_id: str | None = None,
    *,
    vp: int | None = None,
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

    result_ids = {r.pk for r in group["results"]}
    tiebreaks = dict(game.placement_tiebreaks or {})

    if resolution == "tie":
        if target_vp == max_vp:
            game.tied_game = True
            game.designated_winner = None
            game.save(update_fields=["tied_game", "designated_winner"])
        else:
            tiebreaks[str(target_vp)] = "tie"
            game.placement_tiebreaks = tiebreaks
            game.save(update_fields=["placement_tiebreaks"])
        return

    if resolution != "winner" or not winner_result_id:
        raise ValueError(
            "Elige un jugador para el puesto o marca «Empate» en ese grupo."
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
        game.save(update_fields=["tied_game", "designated_winner"])
    else:
        tiebreaks[str(target_vp)] = winner_pk
        game.placement_tiebreaks = tiebreaks
        game.save(update_fields=["placement_tiebreaks"])


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
            apply_tiebreak(game, resolution, winner_id, vp=vp)
            game.refresh_from_db()
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        raise ValueError(" ".join(errors))


def selected_tiebreak_for_group(game: Game, group: dict) -> dict:
    """UI state: resolution and winner pk for one tie group."""
    vp = group["vp"]
    if group["is_winner_group"]:
        if game.tied_game:
            return {"resolution": "tie", "winner_pk": None}
        if game.designated_winner_id:
            return {"resolution": "winner", "winner_pk": game.designated_winner_id}
        return {"resolution": "", "winner_pk": None}

    raw = (game.placement_tiebreaks or {}).get(str(vp))
    if raw == "tie":
        return {"resolution": "tie", "winner_pk": None}
    if raw is not None:
        try:
            return {"resolution": "winner", "winner_pk": int(raw)}
        except (TypeError, ValueError):
            pass
    return {"resolution": "", "winner_pk": None}
