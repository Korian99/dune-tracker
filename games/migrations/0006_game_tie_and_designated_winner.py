from django.db import migrations, models
import django.db.models.deletion


def backfill_designated_winners(apps, schema_editor):
    """Keep prior tie-break behavior: lowest result id among tied max-VP players."""
    Game = apps.get_model("games", "Game")
    GameResult = apps.get_model("games", "GameResult")
    for game in Game.objects.iterator():
        results = list(GameResult.objects.filter(game_id=game.pk))
        if not results:
            continue
        max_vp = max(r.victory_points for r in results)
        leaders = [r for r in results if r.victory_points == max_vp]
        if len(leaders) > 1:
            game.designated_winner_id = min(leaders, key=lambda r: r.pk).pk
            game.save(update_fields=["designated_winner_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0005_import_liga_n1_sheet_games"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="tied_game",
            field=models.BooleanField(
                default=False,
                help_text="No single winner (VP tie acknowledged)",
            ),
        ),
        migrations.AddField(
            model_name="game",
            name="designated_winner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="designated_win_for_game",
                to="games.gameresult",
            ),
        ),
        migrations.RunPython(backfill_designated_winners, noop_reverse),
    ]
