"""
VP tie detection and resolution for games.
"""

from collections import defaultdict

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


def has_top_vp_tie(game: Game) -> bool:
    """True when two or more players share the highest VP (incl. imported games)."""
    return len(game.max_vp_results()) > 1


def game_needs_tiebreak(game: Game) -> bool:
    """True when top VP is shared and winner/tie not recorded yet."""
    if not has_top_vp_tie(game):
        return False
    if game.tied_game:
        return False
    if game.designated_winner_id:
        try:
            return game.designated_winner not in game.max_vp_results()
        except GameResult.DoesNotExist:
            return True
    return True


def normalize_winner_after_save(game: Game) -> None:
    """Clear winner flags that no longer match saved scores."""
    leaders = game.max_vp_results()
    if len(leaders) <= 1:
        if game.tied_game or game.designated_winner_id:
            game.tied_game = False
            game.designated_winner = None
            game.save(update_fields=["tied_game", "designated_winner"])
        return

    leader_ids = {r.pk for r in leaders}
    if game.designated_winner_id and game.designated_winner_id not in leader_ids:
        game.designated_winner = None
        game.tied_game = False
        game.save(update_fields=["tied_game", "designated_winner"])


def apply_tiebreak(game: Game, resolution: str, winner_result_id: str | None = None):
    """Persist tiebreak choice for the top-VP group."""
    leaders = game.max_vp_results()
    leader_ids = {r.pk for r in leaders}

    if resolution == "tie":
        game.tied_game = True
        game.designated_winner = None
        game.save(update_fields=["tied_game", "designated_winner"])
        return

    if resolution != "winner" or not winner_result_id:
        raise ValueError(
            "Elige un ganador entre los empatados o marca «Empate (sin ganador único)»."
        )

    try:
        winner_pk = int(winner_result_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Ganador no válido.") from exc

    if winner_pk not in leader_ids:
        raise ValueError("El ganador debe ser uno de los jugadores empatados arriba.")

    game.tied_game = False
    game.designated_winner_id = winner_pk
    game.save(update_fields=["tied_game", "designated_winner"])
