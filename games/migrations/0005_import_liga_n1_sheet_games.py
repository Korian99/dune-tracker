from django.db import migrations


def import_liga_n1_games(apps, schema_editor):
    League = apps.get_model("games", "League")
    try:
        league = League.objects.get(slug="liga-n1")
    except League.DoesNotExist:
        return

    from games.sheet_io import import_games_for_league
    from games.data.liga_n1_sheet import LIGA_N1_GAMES

    import_games_for_league(league, LIGA_N1_GAMES)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0004_player_model_and_league_roster"),
    ]

    operations = [
        migrations.RunPython(import_liga_n1_games, noop_reverse),
    ]
