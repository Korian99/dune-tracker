"""Create Liga N°0 and import historical Uprising games from Board Games Companion."""

from django.db import migrations


def create_liga_n0_and_import_bgc(apps, schema_editor):
    from games.data.bgc_uprising_import import BGC_UPRISING_GAMES
    from games.defaults import DEFAULT_LEAGUE_SCORING_NOTES, default_league_scoring_config
    from games.hitos import ensure_default_hitos
    from games.models import League
    from games.sheet_io import import_games_for_league

    league, _created = League.objects.get_or_create(
        slug="liga-n0",
        defaults={
            "name": "Liga N°0",
            "description": (
                "Partidas históricas importadas desde Board Games Companion "
                "(app móvil). Sin líderes ni alianzas en el origen."
            ),
            "scoring_notes": DEFAULT_LEAGUE_SCORING_NOTES,
            "scoring_config": default_league_scoring_config(),
        },
    )
    ensure_default_hitos(league)
    import_games_for_league(league, BGC_UPRISING_GAMES)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0011_create_admin_from_env"),
    ]

    operations = [
        migrations.RunPython(create_liga_n0_and_import_bgc, noop_reverse),
    ]
