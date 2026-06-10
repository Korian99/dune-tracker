"""Apply BGC manual placements to Liga N°0 games imported without tiebreak resolution."""

from django.db import migrations


def repair_bgc_placements(apps, schema_editor):
    from games.data.bgc_uprising_import import BGC_UPRISING_GAMES
    from games.models import Game, League
    from games.sheet_io import IMPORT_NOTE_PREFIX, apply_bgc_placements

    try:
        league = League.objects.get(slug="liga-n0")
    except League.DoesNotExist:
        return

    by_key = {g["import_key"]: g for g in BGC_UPRISING_GAMES}
    prefix = IMPORT_NOTE_PREFIX
    for game in Game.objects.filter(league=league, notes__startswith=prefix):
        import_key = game.notes[len(prefix) :]
        game_data = by_key.get(import_key)
        if not game_data:
            continue
        if not any(r.get("bgc_placement") is not None for r in game_data["results"]):
            continue
        apply_bgc_placements(game, game_data["results"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0012_create_liga_n0_and_import_bgc"),
    ]

    operations = [
        migrations.RunPython(repair_bgc_placements, noop_reverse),
    ]
