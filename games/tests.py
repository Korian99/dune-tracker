from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import GameAllianceForm
from .models import Game, GameResult, League, Player, resolve_player
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
        player = resolve_player(name, league=self.league)
        return GameResult.objects.create(
            game=self.game,
            player=player,
            victory_points=vp,
            **kwargs,
        )

    def test_placement_points_four_players(self):
        self._result("A", 12)
        self._result("B", 10)
        self._result("C", 8)
        self._result("D", 6)
        results = {r.player.name: r for r in self.game.results.select_related("player")}
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
        player_name = "Carlos"
        player = resolve_player(player_name, league=self.league)
        for i in range(9):
            g = Game.objects.create(
                league=self.league,
                played_on=date.today() - timedelta(days=i),
                player_count=2,
                rounds=5,
            )
            GameResult.objects.create(
                game=g, player=player, victory_points=10, order=0
            )
            rival = resolve_player("Rival", league=self.league)
            GameResult.objects.create(
                game=g, player=rival, victory_points=5, order=1
            )
        rows = league_standings(self.league)
        carlos = next(r for r in rows if r["player_name"] == player_name)
        self.assertEqual(carlos["games_played"], 9)
        self.assertEqual(carlos["games"], 8)
        self.assertEqual(carlos["games_discarded"], 1)
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
        player_name = "Ana"
        player = resolve_player(player_name, league=self.league)
        for i in range(8):
            g = Game.objects.create(
                league=self.league,
                played_on=date.today() - timedelta(days=i + 1),
                player_count=2,
            )
            GameResult.objects.create(
                game=g, player=player, victory_points=10, order=0
            )
            x = resolve_player("X", league=self.league)
            GameResult.objects.create(game=g, player=x, victory_points=3, order=1)
        bad = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=4,
        )
        GameResult.objects.create(game=bad, player=player, victory_points=3, order=0)
        for n, vp in [("B", 15), ("C", 12), ("D", 10)]:
            p = resolve_player(n, league=self.league)
            GameResult.objects.create(game=bad, player=p, victory_points=vp, order=1)

        rows = league_standings(self.league)
        ana = next(r for r in rows if r["player_name"] == player_name)
        self.assertEqual(ana["games_played"], 9)
        self.assertEqual(ana["games_discarded"], 1)
        self.assertEqual(ana["score_best_n"], 40.0)
        self.assertEqual(ana["score_total"], 41.0)

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


class PlayerModelTests(TestCase):
    def test_resolve_player_adds_to_league_roster(self):
        league = League.objects.create(name="Liga", slug="liga")
        player = resolve_player("  María  ", league=league)
        self.assertEqual(player.name, "María")
        self.assertTrue(league.players.filter(pk=player.pk).exists())

    def test_resolve_player_reuses_same_name(self):
        p1 = resolve_player("Bob")
        p2 = resolve_player("Bob")
        self.assertEqual(p1.pk, p2.pk)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class GameEditTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Liga", slug="liga")
        self.game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        for name, vp in [("Ana", 10), ("Bob", 8)]:
            player = resolve_player(name, league=self.league)
            GameResult.objects.create(
                game=self.game, player=player, victory_points=vp
            )

    def test_edit_page_loads_with_existing_results(self):
        url = reverse("games:edit", kwargs={"pk": self.game.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editar partida")
        self.assertContains(response, "Ana")
        self.assertContains(response, "Bob")

    def test_edit_updates_victory_points(self):
        url = reverse("games:edit", kwargs={"pk": self.game.pk})
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 200)
        results = list(self.game.results.order_by("pk"))
        data = {
            "league": str(self.league.pk),
            "played_on": str(self.game.played_on),
            "player_count": "2",
            "duration_hours": "",
            "duration_minutes_part": "",
            "rounds": "",
            "notes": "",
            "results-TOTAL_FORMS": get_response.context["formset"].total_form_count(),
            "results-INITIAL_FORMS": get_response.context["formset"].initial_form_count(),
            "results-MIN_NUM_FORMS": "0",
            "results-MAX_NUM_FORMS": "6",
            "results-0-id": str(results[0].pk),
            "results-0-player_pick": "Ana",
            "results-0-leader": "",
            "results-0-victory_points": "11",
            "results-0-sardaukar_count": "0",
            "results-1-id": str(results[1].pk),
            "results-1-player_pick": "Bob",
            "results-1-leader": "",
            "results-1-victory_points": "7",
            "results-1-sardaukar_count": "0",
            "alliance_emperor": "",
            "alliance_guild": "",
            "alliance_bene_gesserit": "",
            "alliance_fremen": "",
        }
        for i in range(2, data["results-TOTAL_FORMS"]):
            data[f"results-{i}-player_pick"] = ""
            data[f"results-{i}-leader"] = ""
            data[f"results-{i}-victory_points"] = ""
            data[f"results-{i}-sardaukar_count"] = "0"
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, response.context)
        results[0].refresh_from_db()
        results[1].refresh_from_db()
        self.assertEqual(results[0].victory_points, 11)
        self.assertEqual(results[1].victory_points, 7)


class GameAllianceFormTests(TestCase):
    def test_same_player_can_hold_all_alliances(self):
        form = GameAllianceForm(
            data={
                "alliance_emperor": "Kori",
                "alliance_guild": "Kori",
                "alliance_bene_gesserit": "Kori",
                "alliance_fremen": "Kori",
            },
            player_names=["Kori", "Alex"],
        )
        self.assertTrue(form.is_valid(), form.errors)
