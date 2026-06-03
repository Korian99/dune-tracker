from datetime import date

from django.test import TestCase

from .models import Game, GameResult, League
from .scoring import (
    compute_league_points,
    compute_league_points_breakdown,
    league_standings,
)


class LeagueScoringTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Test Liga", slug="test-liga")
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
        self.assertEqual(
            compute_league_points(results["A"], self.league), 8.0
        )  # 5 + early + 10 + 12
        self.assertEqual(compute_league_points(results["B"], self.league), 4.0)  # 2nd place + VP≥10
        self.assertEqual(compute_league_points(results["C"], self.league), 2.0)
        self.assertEqual(compute_league_points(results["D"], self.league), 1.0)

    def test_winner_round_five_twelve_vp_eight_points(self):
        r = self._result("Winner", 12)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(breakdown["placement_points"], 5)
        self.assertEqual(breakdown["early_win"], 1)
        self.assertEqual(breakdown["vp_ge_10"], 1)
        self.assertEqual(breakdown["vp_ge_12"], 1)
        self.assertEqual(breakdown["vp_ge_15"], 0)
        self.assertEqual(breakdown["total"], 8.0)

    def test_no_early_win_on_round_seven(self):
        self.game.rounds = 7
        self.game.save()
        r = self._result("Winner", 12)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(breakdown["early_win"], 0)
        self.assertEqual(breakdown["total"], 7.0)

    def test_no_early_win_without_rounds(self):
        self.game.rounds = None
        self.game.save()
        r = self._result("Winner", 12)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(breakdown["early_win"], 0)

    def test_fifth_place_zero_placement(self):
        for i, vp in enumerate([15, 12, 10, 8, 5], start=1):
            self._result(f"P{i}", vp)
        fifth = self.game.results.get(player_name="P5")
        breakdown = compute_league_points_breakdown(fifth, self.league)
        self.assertEqual(fifth.placement, 5)
        self.assertEqual(breakdown["placement_points"], 0)

    def test_tied_first_shared_placement_and_bonuses(self):
        self._result("A", 10)
        self._result("B", 10)
        self._result("C", 7)
        a = self.game.results.get(player_name="A")
        b = self.game.results.get(player_name="B")
        c = self.game.results.get(player_name="C")
        self.assertEqual(a.placement, 1)
        self.assertEqual(b.placement, 1)
        self.assertEqual(c.placement, 3)
        for leader in (a, b):
            bd = compute_league_points_breakdown(leader, self.league)
            self.assertEqual(bd["placement_points"], 5)
            self.assertEqual(bd["early_win"], 1)
            self.assertEqual(bd["vp_ge_10"], 1)

    def test_vp_thresholds_stack_at_fifteen(self):
        r = self._result("Champ", 15)
        breakdown = compute_league_points_breakdown(r, self.league)
        self.assertEqual(
            breakdown["vp_ge_10"] + breakdown["vp_ge_12"] + breakdown["vp_ge_15"],
            3,
        )

    def test_victory_points_system_override(self):
        self.league.scoring_config = {"system": "victory_points"}
        self.league.save()
        r = self._result("X", 9)
        self.assertEqual(compute_league_points(r, self.league), 9.0)

    def test_league_standings_aggregate(self):
        self._result("A", 12)
        self._result("B", 8)
        rows = league_standings(self.league)
        by_name = {r["player_name"]: r for r in rows}
        self.assertEqual(by_name["A"]["league_points"], 8.0)
        self.assertEqual(by_name["B"]["league_points"], 3.0)
        self.assertEqual(by_name["A"]["games"], 1)
