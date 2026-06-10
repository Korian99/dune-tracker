from django.db import migrations


def import_liga_n1_games(apps, schema_editor):
    HistoricalLeague = apps.get_model("games", "League")
    try:
        historical = HistoricalLeague.objects.get(slug="liga-n1")
    except HistoricalLeague.DoesNotExist:
        return

    # RunPython gives historical models; import uses the live ORM.
    from games.models import League
    from games.data.liga_n1 import LIGA_N1_GAMES
    from games.integrations.sheet_io import import_games_for_league

    league = League.objects.get(pk=historical.pk)
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
