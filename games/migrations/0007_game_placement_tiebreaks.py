from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0006_game_tie_and_designated_winner"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="placement_tiebreaks",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Per-VP tiebreak: VP string -> winner result pk or 'tie'",
            ),
        ),
    ]
