"""Backfill GameResult.order with competition placement (1 = 1st, …)."""

from django.db import migrations, models


def sync_all_result_orders(apps, schema_editor):
    from games.models import Game
    from games.services.tiebreak import sync_result_orders_for_game

    for game in Game.objects.iterator():
        sync_result_orders_for_game(game)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0013_repair_bgc_placements"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gameresult",
            name="order",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Competition placement (1 = 1st, 2 = 2nd, …); synced after save.",
            ),
        ),
        migrations.RunPython(sync_all_result_orders, noop_reverse),
    ]
