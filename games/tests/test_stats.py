from datetime import date

from django.test import RequestFactory, TestCase

from games.models import Game, GameResult, League, Player, resolve_player
from games.services.stats_queries import (
    aggregate_leader_stats,
    aggregate_player_stats,
    filter_scope_label,
    games_for_filter,
    stats_for_filter,
)


class StatsQueriesTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Liga A", slug="liga-a")
        self.player_a = resolve_player("Ana", league=self.league)
        self.player_b = resolve_player("Bob", league=self.league)

    def _game(self, league=None):
        return Game.objects.create(
            league=league,
            played_on=date.today(),
            player_count=2,
            base_game=Game.BaseGame.UPRISING,
            bloodlines=True,
        )

    def test_filter_single_league(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, leader="Muad'Dib", victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, leader="Chani", victory_points=5, order=1
        )
        qs = games_for_filter(["liga-a"], False)
        self.assertEqual(qs.count(), 1)

    def test_leader_stats_win_rate_and_placement(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, leader="Muad'Dib", victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, leader="Muad'Dib", victory_points=5, order=1
        )
        g2 = self._game(league=self.league)
        GameResult.objects.create(
            game=g2, player=self.player_a, leader="Chani", victory_points=8, order=0
        )
        GameResult.objects.create(
            game=g2, player=self.player_b, leader="Chani", victory_points=12, order=1
        )
        results = GameResult.objects.filter(game__league=self.league)
        leaders = {r["leader"]: r for r in aggregate_leader_stats(results)}
        self.assertEqual(leaders["Muad'Dib"]["times_played"], 2)
        self.assertEqual(leaders["Muad'Dib"]["wins"], 1)
        self.assertEqual(leaders["Muad'Dib"]["win_rate"], 50.0)
        self.assertEqual(leaders["Chani"]["wins"], 1)

    def test_leader_stats_placement_counts(self):
        g1 = self._game(league=self.league)
        GameResult.objects.create(
            game=g1, player=self.player_a, leader="Muad'Dib", victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g1, player=self.player_b, leader="Chani", victory_points=5, order=1
        )
        g2 = self._game(league=self.league)
        GameResult.objects.create(
            game=g2, player=self.player_a, leader="Muad'Dib", victory_points=5, order=0
        )
        GameResult.objects.create(
            game=g2, player=self.player_b, leader="Chani", victory_points=10, order=1
        )
        results = GameResult.objects.filter(game__league=self.league)
        leaders = {r["leader"]: r for r in aggregate_leader_stats(results)}
        self.assertEqual(leaders["Muad'Dib"]["placement_1"], 1)
        self.assertEqual(leaders["Muad'Dib"]["placement_2"], 1)
        self.assertEqual(leaders["Chani"]["placement_1"], 1)
        self.assertEqual(leaders["Chani"]["placement_2"], 1)
        self.assertEqual(leaders["Muad'Dib"]["placement_3"], 0)
        self.assertEqual(leaders["Muad'Dib"]["placement_4"], 0)

    def test_leader_stats_filtered_by_player(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, leader="Muad'Dib", victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, leader="Chani", victory_points=5, order=1
        )
        g2 = self._game(league=self.league)
        GameResult.objects.create(
            game=g2, player=self.player_a, leader="Chani", victory_points=12, order=0
        )
        GameResult.objects.create(
            game=g2, player=self.player_b, leader="Muad'Dib", victory_points=8, order=1
        )
        all_results = GameResult.objects.filter(game__league=self.league)
        all_leaders = {r["leader"]: r for r in aggregate_leader_stats(all_results)}
        ana_results = all_results.filter(player=self.player_a)
        ana_leaders = {r["leader"]: r for r in aggregate_leader_stats(ana_results)}
        self.assertEqual(all_leaders["Muad'Dib"]["times_played"], 2)
        self.assertEqual(ana_leaders["Muad'Dib"]["times_played"], 1)
        self.assertEqual(ana_leaders["Chani"]["times_played"], 1)
        self.assertEqual(ana_leaders["Chani"]["wins"], 1)

    def test_stats_for_filter_leader_player_filter(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, leader="Muad'Dib", victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, leader="Chani", victory_points=5, order=1
        )
        g2 = self._game(league=self.league)
        GameResult.objects.create(
            game=g2, player=self.player_a, leader="Chani", victory_points=12, order=0
        )
        GameResult.objects.create(
            game=g2, player=self.player_b, leader="Muad'Dib", victory_points=8, order=1
        )
        data = stats_for_filter(["liga-a"], False, player_slugs=[self.player_a.slug])
        by_leader = {r["leader"]: r for r in data["leader_rows"]}
        self.assertEqual(by_leader["Muad'Dib"]["times_played"], 1)
        self.assertEqual(by_leader["Chani"]["times_played"], 1)
        self.assertEqual(data["leader_filter_label"], "Ana")
        unfiltered = stats_for_filter(["liga-a"], False)
        self.assertEqual(
            {r["leader"]: r for r in unfiltered["leader_rows"]}["Muad'Dib"]["times_played"],
            2,
        )

    def test_stats_for_filter_includes_leader_placement_counts(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, leader="Muad'Dib", victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, leader="Chani", victory_points=5, order=1
        )
        data = stats_for_filter(["liga-a"], False)
        by_leader = {r["leader"]: r for r in data["leader_rows"]}
        self.assertEqual(by_leader["Muad'Dib"]["placement_1"], 1)
        self.assertEqual(by_leader["Chani"]["placement_2"], 1)

    def test_stats_for_filter_uses_league_standings_when_one_league(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, victory_points=5, order=1
        )
        data = stats_for_filter(["liga-a"], False)
        self.assertTrue(data["use_league_scoring"])
        self.assertEqual(len(data["player_rows"]), 2)

    def test_scope_label_all(self):
        self.assertEqual(filter_scope_label([], False), "Todas las partidas")

    def test_player_stats_placement_counts(self):
        g1 = self._game(league=self.league)
        GameResult.objects.create(
            game=g1, player=self.player_a, victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g1, player=self.player_b, victory_points=5, order=1
        )
        g2 = self._game(league=self.league)
        GameResult.objects.create(
            game=g2, player=self.player_a, victory_points=5, order=0
        )
        GameResult.objects.create(
            game=g2, player=self.player_b, victory_points=10, order=1
        )
        results = GameResult.objects.filter(game__league=self.league)
        rows = {r["name"]: r for r in aggregate_player_stats(results)}
        self.assertEqual(rows["Ana"]["placement_1"], 1)
        self.assertEqual(rows["Ana"]["placement_2"], 1)
        self.assertEqual(rows["Bob"]["placement_1"], 1)
        self.assertEqual(rows["Bob"]["placement_2"], 1)

    def test_wins_match_first_place_count(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, victory_points=10, order=1
        )
        results = GameResult.objects.filter(game__league=self.league)
        rows = {r["name"]: r for r in aggregate_player_stats(results)}
        self.assertEqual(rows["Ana"]["placement_1"], 1)
        self.assertEqual(rows["Bob"]["placement_1"], 1)
        self.assertEqual(rows["Ana"]["wins"], rows["Ana"]["placement_1"])
        self.assertEqual(rows["Bob"]["wins"], rows["Bob"]["placement_1"])

    def test_single_league_stats_attaches_placement_counts(self):
        g = self._game(league=self.league)
        GameResult.objects.create(
            game=g, player=self.player_a, victory_points=10, order=0
        )
        GameResult.objects.create(
            game=g, player=self.player_b, victory_points=5, order=1
        )
        data = stats_for_filter(["liga-a"], False)
        by_name = {r["player_name"]: r for r in data["player_rows"]}
        self.assertEqual(by_name["Ana"]["placement_1"], 1)
        self.assertEqual(by_name["Ana"]["placement_2"], 0)
        self.assertEqual(by_name["Bob"]["placement_2"], 1)
