from django.db import migrations, models
import django.db.models.deletion


def seed_default_hitos(apps, schema_editor):
    League = apps.get_model("games", "League")
    LeagueHito = apps.get_model("games", "LeagueHito")
    specs = (
        ("highscore", "Highscore", "Mayor puntuación de liga en una sola partida.", "max_league_points", 0),
        ("powerscore", "Powerscore", "Más puntos de victoria (PV) en una sola partida.", "max_victory_points", 1),
        ("lowscore", "Lowscore", "Menor puntuación de liga en una sola partida.", "min_league_points", 2),
    )
    for league in League.objects.iterator():
        for slug, name, description, metric, order in specs:
            LeagueHito.objects.get_or_create(
                league_id=league.pk,
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "metric": metric,
                    "order": order,
                    "is_builtin": True,
                    "is_active": True,
                },
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0007_game_placement_tiebreaks"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeagueHito",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("slug", models.SlugField(max_length=40)),
                (
                    "name",
                    models.CharField(
                        help_text="Display name (personalizable por liga).",
                        max_length=80,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "metric",
                    models.CharField(
                        choices=[
                            (
                                "max_league_points",
                                "Máx. puntos de liga (una partida)",
                            ),
                            ("max_victory_points", "Máx. PV (una partida)"),
                            (
                                "min_league_points",
                                "Mín. puntos de liga (una partida)",
                            ),
                        ],
                        max_length=32,
                    ),
                ),
                ("order", models.PositiveSmallIntegerField(default=0)),
                (
                    "is_builtin",
                    models.BooleanField(
                        default=False,
                        help_text="True for highscore / powerscore / lowscore seeded on create.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "league",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hitos",
                        to="games.league",
                    ),
                ),
            ],
            options={
                "verbose_name": "league hito",
                "verbose_name_plural": "league hitos",
                "ordering": ["order", "slug"],
            },
        ),
        migrations.AddConstraint(
            model_name="leaguehito",
            constraint=models.UniqueConstraint(
                fields=("league", "slug"),
                name="unique_hito_slug_per_league",
            ),
        ),
        migrations.RunPython(seed_default_hitos, noop_reverse),
    ]
