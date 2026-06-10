from datetime import date
from pathlib import Path

from django.test import TestCase

from .bgc_io import BGC_IMPORT_PREFIX, games_from_bgc_directory
from .bgc_hive import load_players
from .data.bgc_uprising_import import BGC_UPRISING_GAMES
from .models import Game, GameResult, League, resolve_player
from .sheet_io import apply_bgc_placements, import_games_for_league

BACKUP = Path(__file__).resolve().parent.parent / "_bgc_backup_extract"


class BgcImportTests(TestCase):
    def test_translate_uprising_games_from_backup(self):
        if not (BACKUP / "playthroughs.hive").exists():
            self.skipTest("BGC backup extract not present locally")
        games = games_from_bgc_directory(BACKUP)
        self.assertGreaterEqual(len(games), 70)
        game = games[0]
        self.assertTrue(game["import_key"].startswith(BGC_IMPORT_PREFIX))
        self.assertIsInstance(game["played_on"], date)
        self.assertGreaterEqual(len(game["results"]), 2)
        self.assertLessEqual(max(r["victory_points"] for r in game["results"]), 20)

    def test_players_include_known_names(self):
        if not (BACKUP / "players.hive").exists():
            self.skipTest("BGC backup extract not present locally")
        players = load_players(BACKUP / "players.hive")
        self.assertIn("Roger", players.values())
        self.assertIn("Pitufo", players.values())

    def test_bundled_module_imports_one_game(self):
        league = League.objects.create(name="BGC", slug="bgc-test")
        sample = [BGC_UPRISING_GAMES[0]]
        created, skipped = import_games_for_league(league, sample)
        self.assertEqual(created, 1)
        created2, skipped2 = import_games_for_league(league, sample)
        self.assertEqual(created2, 0)
        self.assertEqual(skipped2, 1)

    def test_apply_bgc_placements_resolves_vp_tie(self):
        league = League.objects.create(name="BGC tie", slug="bgc-tie")
        game = Game.objects.create(
            league=league,
            played_on=date.today(),
            player_count=2,
            base_game=Game.BaseGame.UPRISING,
            bloodlines=True,
        )
        a = resolve_player("Ana", league=league)
        b = resolve_player("Bob", league=league)
        ra = GameResult.objects.create(game=game, player=a, victory_points=10)
        rb = GameResult.objects.create(game=game, player=b, victory_points=10)
        apply_bgc_placements(
            game,
            [
                {"player": "Ana", "bgc_placement": 2},
                {"player": "Bob", "bgc_placement": 1},
            ],
        )
        self.assertEqual(ra.placement, 2)
        self.assertEqual(rb.placement, 1)
        self.assertTrue(rb.is_winner)
        self.assertFalse(ra.is_winner)

    def test_liga_n0_migration_imports_bgc_games(self):
        import importlib

        migration = importlib.import_module(
            "games.migrations.0012_create_liga_n0_and_import_bgc"
        )
        create_liga_n0_and_import_bgc = migration.create_liga_n0_and_import_bgc

        create_liga_n0_and_import_bgc(None, None)
        league = League.objects.get(slug="liga-n0")
        self.assertEqual(league.name, "Liga N°0")
        self.assertEqual(Game.objects.filter(league=league).count(), len(BGC_UPRISING_GAMES))
        create_liga_n0_and_import_bgc(None, None)
        self.assertEqual(Game.objects.filter(league=league).count(), len(BGC_UPRISING_GAMES))
