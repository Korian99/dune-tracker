"""Drop legacy tiebreak fields; order on GameResult is the source of truth."""

from collections import defaultdict

from django.db import migrations


def _old_game_needs_tiebreak(game, results) -> bool:
    """Pre-order tiebreak detection using placement_tiebreaks / designated_winner."""
    by_vp = defaultdict(list)
    for result in results:
        by_vp[result.victory_points].append(result)
    if not by_vp:
        return False
    max_vp = max(by_vp.keys())
    tiebreaks = game.placement_tiebreaks or {}

    for vp, group in by_vp.items():
        if len(group) < 2:
            continue
        group_pks = {r.pk for r in group}
        raw = tiebreaks.get(str(vp))
        if raw == "tie":
            continue
        if isinstance(raw, list):
            try:
                pks = [int(x) for x in raw]
            except (TypeError, ValueError):
                pks = []
            if len(pks) == len(group_pks) and set(pks) == group_pks:
                continue
        if vp == max_vp:
            if game.tied_game:
                continue
            if game.designated_winner_id and game.designated_winner_id in group_pks:
                continue
        elif raw is not None and raw != "tie":
            try:
                pk = int(raw)
            except (TypeError, ValueError):
                pk = None
            if pk in group_pks:
                continue
        return True
    return False


def reset_unresolved_tie_orders(apps, schema_editor):
    """Mark unresolved VP tie groups with order=0 before removing JSON/FK fields."""
    Game = apps.get_model("games", "Game")
    GameResult = apps.get_model("games", "GameResult")

    for game in Game.objects.iterator():
        results = list(GameResult.objects.filter(game_id=game.pk))
        if not _old_game_needs_tiebreak(game, results):
            continue
        by_vp = defaultdict(list)
        for result in results:
            by_vp[result.victory_points].append(result)
        unresolved_pks: set[int] = set()
        for group in by_vp.values():
            if len(group) >= 2:
                unresolved_pks.update(r.pk for r in group)
        if unresolved_pks:
            GameResult.objects.filter(pk__in=unresolved_pks).update(order=0)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0014_sync_result_order_to_placement"),
    ]

    operations = [
        migrations.RunPython(reset_unresolved_tie_orders, noop_reverse),
        migrations.RemoveField(
            model_name="game",
            name="designated_winner",
        ),
        migrations.RemoveField(
            model_name="game",
            name="placement_tiebreaks",
        ),
        migrations.RemoveField(
            model_name="game",
            name="tied_game",
        ),
    ]
