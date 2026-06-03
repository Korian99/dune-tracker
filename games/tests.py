from datetime import date, timedelta

from django.test import TestCase

from .models import Game, GameResult, League
from .scoring import (
    compute_league_points,
    compute_league_points_breakdown,
    config_from_form_data,
    default_scoring_config,
    league_standings,
    resolve_scoring_config,
)


class LeagueScoringTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(
            name="Test Liga",
            slug="test-liga",
            scoring_config=default_scoring_config(),
        )
        self.game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=4,
            rounds=5,
        )

    def _result(self, name, vp, **kwargs):
        return GameResult.objects.create(
            game=self.game,
            player_name=name,
            victory_points=vp,
            **kwargs,
        )

    def test_placement_points_four_players(self):
        self._result("A", 12)
        self._result("B", 10)
        self._result("C", 8)
        self._result("D", 6)
        results = {r.player_name: r for r in self.game.results.all()}
        self.assertEqual(compute_league_points(results["A"], self.league), 8.0)
        self.assertEqual(compute_league_points(results["B"], self.league), 4.0)
        self.assertEqual(compute_league_points(results["C"], self.league), 2.0)
        self.assertEqual(compute_league_points(results["D"], self.league), 1.0)

    def test_winner_round_five_twelve_vp_eight_points(self):
        r = self._result("Winner", 12)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(breakdown["placement_points"], 5)
        self.assertEqual(breakdown["early_win"], 1)
        self.assertEqual(breakdown["vp_threshold_bonuses"], 2)
        self.assertEqual(breakdown["total"], 8.0)

    def test_no_early_win_on_round_seven(self):
        self.game.rounds = 7
        self.game.save()
        r = self._result("Winner", 12)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(breakdown["early_win"], 0)
        self.assertEqual(breakdown["total"], 7.0)

    def test_custom_config_from_league(self):
        self.league.scoring_config = {
            "count_games": 8,
            "placement_points": {1: 10, 2: 5, 3: 0, 4: 0},
            "early_win_max_round": 0,
            "vp_thresholds": [],
        }
        self.league.save()
        r = self._result("Solo", 5)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(breakdown["placement_points"], 10)
        self.assertEqual(breakdown["total"], 10.0)

    def test_best_eight_counts_only_eight_games(self):
        player = "Carlos"
        for i in range(9):
            g = Game.objects.create(
                league=self.league,
                played_on=date.today() - timedelta(days=i),
                player_count=2,
                rounds=5,
            )
            GameResult.objects.create(
                game=g, player_name=player, victory_points=10, order=0
            )
            GameResult.objects.create(
                game=g, player_name="Rival", victory_points=5, order=1
            )
        rows = league_standings(self.league)
        carlos = next(r for r in rows if r["player_name"] == player)
        self.assertEqual(carlos["games_played"], 9)
        self.assertEqual(carlos["games"], 8)
        self.assertEqual(carlos["games_discarded"], 1)
        # Nine games at 7 league pts each (10 PV) → sum best 8 = 56
        self.assertEqual(carlos["league_points"], 56.0)

    def test_ninth_worst_score_discarded(self):
        """Player with 9 games: lowest league-point game is excluded."""
        self.league.scoring_config = {
            **default_scoring_config(),
            "count_games": 8,
            "vp_thresholds": [],
            "early_win_max_round": 0,
        }
        self.league.save()
        player = "Ana"
        # 8 wins at 5 pts (1st only) + 1 game at 1 pt (4th)
        for i in range(8):
            g = Game.objects.create(
                league=self.league,
                played_on=date.today() - timedelta(days=i + 1),
                player_count=2,
            )
            GameResult.objects.create(
                game=g, player_name=player, victory_points=10, order=0
            )
            GameResult.objects.create(
                game=g, player_name="X", victory_points=3, order=1
            )
        bad = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=4,
        )
        GameResult.objects.create(game=bad, player_name=player, victory_points=3, order=0)
        for n, vp in [("B", 15), ("C", 12), ("D", 10)]:
            GameResult.objects.create(game=bad, player_name=n, victory_points=vp, order=1)

        rows = league_standings(self.league)
        ana = next(r for r in rows if r["player_name"] == player)
        self.assertEqual(ana["games_played"], 9)
        self.assertEqual(ana["games_discarded"], 1)
        # 8 * 5 + 0 (4th place game discarded) = 40
        self.assertEqual(ana["league_points"], 40.0)

    def test_victory_points_system_override(self):
        self.league.scoring_config = {"system": "victory_points", "count_games": 8}
        self.league.save()
        r = self._result("X", 9)
        self.assertEqual(compute_league_points(r, self.league), 9.0)

    def test_config_from_form_data(self):
        cfg = config_from_form_data(
            {
                "count_games": 5,
                "points_1st": 4,
                "points_2nd": 2,
                "points_3rd": 1,
                "points_4th": 0,
                "early_win_max_round": 5,
                "vp_bonus_10": True,
                "vp_bonus_12": False,
                "vp_bonus_15": True,
            }
        )
        self.assertEqual(cfg["count_games"], 5)
        self.assertEqual(cfg["placement_points"][1], 4)
        self.assertEqual(cfg["vp_thresholds"], [10, 15])

    def test_resolve_merges_empty_league_config(self):
        empty = League.objects.create(name="Empty", slug="empty")
        cfg = resolve_scoring_config(empty)
        self.assertEqual(cfg["count_games"], 8)
        self.assertEqual(cfg["placement_points"][1], 5)
