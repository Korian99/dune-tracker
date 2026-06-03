from django.db import migrations, models
import django.db.models.deletion


def remap_hito_metrics(apps, schema_editor):
    LeagueHito = apps.get_model("games", "LeagueHito")
    mapping = {
        "highscore": "auto_max_vp",
        "lowscore": "auto_min_vp",
        "powerscore": "manual",
        "max_league_points": "auto_max_vp",
        "max_victory_points": "auto_max_vp",
        "min_league_points": "auto_min_vp",
    }
    for hito in LeagueHito.objects.iterator():
        new_metric = mapping.get(hito.slug) or mapping.get(hito.metric)
        if new_metric and hito.metric != new_metric:
            hito.metric = new_metric
            hito.save(update_fields=["metric"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0008_league_hito"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaguehito",
            name="manual_value",
            field=models.CharField(
                blank=True,
                help_text="Powerscore: texto libre (p. ej. récord o nota de la liga).",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="leaguehito",
            name="manual_player",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="powerscore_hitos",
                to="games.player",
            ),
        ),
        migrations.AlterField(
            model_name="leaguehito",
            name="metric",
            field=models.CharField(
                choices=[
                    ("auto_max_vp", "Mayor PV (automático)"),
                    ("auto_min_vp", "Menor PV (automático)"),
                    ("manual", "Manual"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(remap_hito_metrics, noop_reverse),
    ]
