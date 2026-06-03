import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models
from django.utils.text import slugify


def _player_slug(Player, name, used_slugs):
    base = slugify(name) or "player"
    slug = base
    n = 1
    while slug in used_slugs or Player.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    used_slugs.add(slug)
    return slug


def migrate_player_names_forward(apps, schema_editor):
    GameResult = apps.get_model("games", "GameResult")
    Player = apps.get_model("games", "Player")
    LeagueMembership = apps.get_model("games", "LeagueMembership")

    used_slugs = set(Player.objects.values_list("slug", flat=True))
    name_to_player = {}

    def get_player(name):
        normalized = " ".join((name or "").split())
        if not normalized:
            return None
        if normalized in name_to_player:
            return name_to_player[normalized]
        player, created = Player.objects.get_or_create(
            name=normalized,
            defaults={"slug": _player_slug(Player, normalized, used_slugs)},
        )
        if created and not player.slug:
            player.slug = _player_slug(Player, normalized, used_slugs)
            player.save(update_fields=["slug"])
        name_to_player[normalized] = player
        return player

    for result in GameResult.objects.select_related("game").iterator():
        player = get_player(result.player_name)
        if not player:
            continue
        result.player_id = player.pk
        result.save(update_fields=["player_id"])
        if result.game.league_id:
            LeagueMembership.objects.get_or_create(
                league_id=result.game.league_id,
                player_id=player.pk,
                defaults={"joined_at": django.utils.timezone.now()},
            )


def migrate_player_names_backward(apps, schema_editor):
    GameResult = apps.get_model("games", "GameResult")
    Player = apps.get_model("games", "Player")
    for result in GameResult.objects.select_related("player").iterator():
        if result.player_id:
            result.player_name = Player.objects.get(pk=result.player_id).name
            result.save(update_fields=["player_name"])


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0003_default_league_scoring_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="Player",
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
                ("name", models.CharField(max_length=80, unique=True)),
                ("slug", models.SlugField(blank=True, max_length=80, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="LeagueMembership",
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
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "league",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="games.league",
                    ),
                ),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="games.player",
                    ),
                ),
            ],
            options={
                "ordering": ["player__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="leaguemembership",
            constraint=models.UniqueConstraint(
                fields=("league", "player"), name="unique_league_player"
            ),
        ),
        migrations.AddField(
            model_name="league",
            name="players",
            field=models.ManyToManyField(
                related_name="leagues",
                through="games.LeagueMembership",
                to="games.player",
            ),
        ),
        migrations.AddField(
            model_name="gameresult",
            name="player",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="game_results",
                to="games.player",
            ),
        ),
        migrations.RunPython(
            migrate_player_names_forward,
            migrate_player_names_backward,
        ),
        migrations.RemoveConstraint(
            model_name="gameresult",
            name="unique_player_per_game",
        ),
        migrations.RemoveField(
            model_name="gameresult",
            name="player_name",
        ),
        migrations.AlterField(
            model_name="gameresult",
            name="player",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="game_results",
                to="games.player",
            ),
        ),
        migrations.AddConstraint(
            model_name="gameresult",
            constraint=models.UniqueConstraint(
                fields=("game", "player"), name="unique_player_per_game"
            ),
        ),
    ]
