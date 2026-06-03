from datetime import date

from django.test import TestCase

from .forms import LeagueForm
from .hitos import ensure_default_hitos, league_hito_snapshots
from .models import Game, GameResult, League, LeagueHito, resolve_player


class LeagueHitoTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Hito Liga", slug="hito-liga")

    def test_ensure_default_hitos_creates_three(self):
        created = ensure_default_hitos(self.league)
        self.assertEqual(len(created), 3)
        slugs = set(self.league.hitos.values_list("slug", flat=True))
        self.assertEqual(slugs, {"highscore", "powerscore", "lowscore"})

    def test_league_form_seeds_hitos_on_create(self):
        form = LeagueForm(
            data={
                "name": "Nueva",
                "description": "",
                "scoring_notes": "",
                "count_games": 8,
                "points_1st": 5,
                "points_2nd": 3,
                "points_3rd": 2,
                "points_4th": 1,
                "early_win_max_round": 6,
                "vp_bonus_10": True,
                "vp_bonus_12": True,
                "vp_bonus_15": True,
            }
        )
        self.assertTrue(form.is_valid())
        league = form.save()
        self.assertEqual(league.hitos.count(), 3)

    def test_snapshots_track_high_power_low(self):
        ensure_default_hitos(self.league)
        game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
            rounds=5,
        )
        ana = resolve_player("Ana", league=self.league)
        bob = resolve_player("Bob", league=self.league)
        GameResult.objects.create(game=game, player=ana, victory_points=12, order=0)
        GameResult.objects.create(game=game, player=bob, victory_points=6, order=1)

        game2 = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        GameResult.objects.create(game=game2, player=ana, victory_points=8, order=0)
        GameResult.objects.create(game=game2, player=bob, victory_points=8, order=1)

        snapshots = {s["hito"].slug: s for s in league_hito_snapshots(self.league)}

        high = snapshots["highscore"]
        self.assertFalse(high["empty"])
        self.assertEqual(high["holders"][0]["player_name"], "Ana")
        self.assertEqual(high["value"], 8.0)

        power = snapshots["powerscore"]
        self.assertEqual(power["value"], 12)
        self.assertEqual(power["value_label"], "12 PV")

        low = snapshots["lowscore"]
        self.assertEqual(low["value"], 3.0)
        self.assertEqual(low["holders"][0]["player_name"], "Bob")

    def test_custom_hito_name(self):
        ensure_default_hitos(self.league)
        hito = self.league.hitos.get(slug="highscore")
        hito.name = "Mejor partida"
        hito.save()
        snapshots = league_hito_snapshots(self.league)
        self.assertEqual(snapshots[0]["hito"].name, "Mejor partida")

    def test_inactive_hito_hidden(self):
        ensure_default_hitos(self.league)
        self.league.hitos.filter(slug="lowscore").update(is_active=False)
        slugs = [s["hito"].slug for s in league_hito_snapshots(self.league)]
        self.assertNotIn("lowscore", slugs)

    def test_custom_metric_hito(self):
        LeagueHito.objects.create(
            league=self.league,
            slug="custom-max-vp",
            name="PV loco",
            metric=LeagueHito.Metric.MAX_VICTORY_POINTS,
            order=10,
        )
        game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        p = resolve_player("X", league=self.league)
        GameResult.objects.create(game=game, player=p, victory_points=15)
        snap = next(
            s for s in league_hito_snapshots(self.league) if s["hito"].slug == "custom-max-vp"
        )
        self.assertEqual(snap["value"], 15)
