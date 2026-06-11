from datetime import date
from pathlib import Path

from django.test import TestCase

from games.integrations.bgc.io import BGC_IMPORT_PREFIX, games_from_bgc_directory
from games.integrations.bgc.names import normalize_bgc_player_name
from games.integrations.bgc.hive import load_players
from games.integrations.bgc.leader_sync import merge_leaders_into_games, parse_import_key_from_notes
from games.data.bgc_uprising import BGC_UPRISING_GAMES
from games.models import Game, GameResult, League, resolve_player
from games.integrations.sheet_io import apply_bgc_placements, import_games_for_league, import_note_key

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

    def test_normalize_bgc_player_name_aliases(self):
        self.assertEqual(normalize_bgc_player_name("kori"), "Kori")
        self.assertEqual(normalize_bgc_player_name("KORI"), "Kori")
        self.assertEqual(normalize_bgc_player_name("Matute"), "Matías")
        self.assertEqual(normalize_bgc_player_name("Roger"), "Roger")

    def test_bgc_export_uses_canonical_player_names(self):
        if not (BACKUP / "playthroughs.hive").exists():
            self.skipTest("BGC backup extract not present locally")
        games = games_from_bgc_directory(BACKUP)
        names = {r["player"] for g in games for r in g["results"]}
        self.assertNotIn("kori", names)
        self.assertNotIn("Matute", names)
        raw_names = {n.casefold() for n in load_players(BACKUP / "players.hive").values()}
        if "kori" in raw_names:
            self.assertIn("Kori", names)
        if "matute" in raw_names:
            self.assertIn("Matías", names)

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

    def test_parse_import_key_from_notes(self):
        self.assertEqual(
            parse_import_key_from_notes(import_note_key("bgc-abc")),
            "bgc-abc",
        )
        self.assertIsNone(parse_import_key_from_notes(""))
        self.assertIsNone(parse_import_key_from_notes("casual game"))

    def test_merge_leaders_matches_by_player_name(self):
        games_data = [
            {
                "import_key": "bgc-test-1",
                "results": [
                    {"player": "Roger", "leader": "", "victory_points": 12},
                    {"player": "Pitufo", "leader": "", "victory_points": 8},
                ],
            }
        ]
        live_games = [
            {
                "import_key": "bgc-test-1",
                "results": [
                    {"player_name": "Roger", "leader": "Paul Atreides", "victory_points": 12},
                    {"player_name": "Pitufo", "leader": "Chani", "victory_points": 8},
                ],
            }
        ]
        count, warnings = merge_leaders_into_games(games_data, live_games)
        self.assertEqual(count, 2)
        self.assertEqual(warnings, [])
        self.assertEqual(games_data[0]["results"][0]["leader"], "Paul Atreides")
        self.assertEqual(games_data[0]["results"][1]["leader"], "Chani")

    def test_merge_leaders_vp_fallback_when_names_differ(self):
        games_data = [
            {
                "import_key": "bgc-test-2",
                "results": [
                    {"player": "Matías", "leader": "", "victory_points": 11},
                    {"player": "Kori", "leader": "", "victory_points": 9},
                ],
            }
        ]
        live_games = [
            {
                "import_key": "bgc-test-2",
                "results": [
                    {"player_name": "Matute", "leader": "Gurney Halleck", "victory_points": 11},
                    {"player_name": "kori", "leader": "Stilgar", "victory_points": 9},
                ],
            }
        ]
        count, warnings = merge_leaders_into_games(games_data, live_games)
        self.assertEqual(count, 2)
        self.assertEqual(warnings, [])
        self.assertEqual(games_data[0]["results"][0]["leader"], "Gurney Halleck")
        self.assertEqual(games_data[0]["results"][1]["leader"], "Stilgar")

    def test_merge_leaders_skips_empty_live_leader(self):
        games_data = [
            {
                "import_key": "bgc-test-3",
                "results": [
                    {"player": "Roger", "leader": "", "victory_points": 10},
                ],
            }
        ]
        live_games = [
            {
                "import_key": "bgc-test-3",
                "results": [
                    {"player_name": "Roger", "leader": "", "victory_points": 10},
                ],
            }
        ]
        count, warnings = merge_leaders_into_games(games_data, live_games)
        self.assertEqual(count, 0)
        self.assertEqual(games_data[0]["results"][0]["leader"], "")

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
