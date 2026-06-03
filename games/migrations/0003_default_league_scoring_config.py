# Generated manually — seed standard league scoring defaults.

from django.db import migrations, models

import games.defaults


def _needs_standard_default(config) -> bool:
    if not config:
        return True
    if config.get("system") == "victory_points":
        return False
    required = ("count_games", "placement_points", "early_win_max_round", "vp_thresholds")
    return any(key not in config for key in required)


def seed_league_scoring(apps, schema_editor):
    League = apps.get_model("games", "League")
    default_config = games.defaults.default_league_scoring_config()
    default_notes = games.defaults.DEFAULT_LEAGUE_SCORING_NOTES.strip()

    for league in League.objects.all():
        config = league.scoring_config or {}
        updated = False

        if _needs_standard_default(config):
            league.scoring_config = default_config
            updated = True
        elif config.get("system") == "victory_points" and "count_games" not in config:
            league.scoring_config = {**default_config, **config}
            updated = True

        if not (league.scoring_notes or "").strip():
            league.scoring_notes = default_notes
            updated = True

        if updated:
            league.save(update_fields=["scoring_config", "scoring_notes"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0002_league_game_duration_minutes_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="league",
            name="scoring_config",
            field=models.JSONField(
                blank=True,
                default=games.defaults.default_league_scoring_config,
                help_text="Structured scoring JSON — see games/defaults.py and games/scoring.py",
            ),
        ),
        migrations.RunPython(seed_league_scoring, noop_reverse),
    ]
