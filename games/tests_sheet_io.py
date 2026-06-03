from datetime import date

from django.test import TestCase

from .data.liga_n1_sheet import LIGA_N1_GAMES
from .models import Game, GameResult, League, Player
from .sheet_io import (
    export_league_sheet,
    format_duration_minutes,
    import_games_for_league,
    parse_duration_minutes,
    parse_sheet_date,
)


class SheetIoTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Liga N°1", slug="liga-n1")

    def test_parse_helpers(self):
        self.assertEqual(parse_sheet_date("16/5/26"), date(2026, 5, 16))
        self.assertEqual(parse_duration_minutes("1:25"), 85)
        self.assertEqual(format_duration_minutes(125), "2:05")

    def test_import_liga_n1_idempotent(self):
        created, skipped = import_games_for_league(self.league, LIGA_N1_GAMES)
        self.assertEqual(created, 11)
        self.assertEqual(skipped, 0)
        self.assertEqual(self.league.games.count(), 11)
        self.assertEqual(Player.objects.count(), 6)

        created2, skipped2 = import_games_for_league(self.league, LIGA_N1_GAMES)
        self.assertEqual(created2, 0)
        self.assertEqual(skipped2, 11)

    def test_import_creates_alliances_and_sardaukars(self):
        import_games_for_league(self.league, LIGA_N1_GAMES[1:2])
        game = self.league.games.get()
        anita = game.results.get(player__name="Anita")
        self.assertTrue(anita.alliance_guild)
        self.assertTrue(anita.alliance_fremen)
        self.assertEqual(anita.victory_points, 12)

    def test_export_includes_games(self):
        import_games_for_league(self.league, LIGA_N1_GAMES[:2])
        text = export_league_sheet(self.league)
        self.assertIn("Roger", text)
        self.assertIn("Steersman Y'Rkoon", text)
        self.assertIn("16/5/26", text)
        self.assertIn("||", text)
