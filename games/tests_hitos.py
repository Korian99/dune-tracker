from datetime import date

from django.test import TestCase

from .forms import LeagueForm
from .hitos import ensure_default_hitos, league_hito_snapshots, powerscore_hito
from .models import Game, GameResult, League, LeagueHito, resolve_player


class LeagueHitoTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Hito Liga", slug="hito-liga")

    def test_ensure_default_hitos_creates_three(self):
        created = ensure_default_hitos(self.league)
        self.assertEqual(len(created), 3)
        slugs = set(self.league.hitos.values_list("slug", flat=True))
        self.assertEqual(slugs, {"highscore", "powerscore", "lowscore"})
        metrics = dict(self.league.hitos.values_list("slug", "metric"))
        self.assertEqual(metrics["highscore"], LeagueHito.Metric.AUTO_MAX_VP)
        self.assertEqual(metrics["powerscore"], LeagueHito.Metric.MANUAL)
        self.assertEqual(metrics["lowscore"], LeagueHito.Metric.AUTO_MIN_VP)

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
                "vp_thresholds": "10, 12, 15",
            }
        )
        self.assertTrue(form.is_valid())
        league = form.save()
        self.assertEqual(league.hitos.count(), 3)

    def test_snapshots_high_and_low_vp(self):
        ensure_default_hitos(self.league)
        game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        ana = resolve_player("Ana", league=self.league)
        bob = resolve_player("Bob", league=self.league)
        GameResult.objects.create(game=game, player=ana, victory_points=12, order=0)
        GameResult.objects.create(game=game, player=bob, victory_points=6, order=1)

        snapshots = {s["hito"].slug: s for s in league_hito_snapshots(self.league)}

        high = snapshots["highscore"]
        self.assertFalse(high["empty"])
        self.assertEqual(high["value"], 12)
        self.assertEqual(high["value_label"], "12 PV")
        self.assertEqual(high["holders"][0]["player_name"], "Ana")

        low = snapshots["lowscore"]
        self.assertEqual(low["value"], 6)
        self.assertEqual(low["holders"][0]["player_name"], "Bob")

        power = snapshots["powerscore"]
        self.assertTrue(power["empty"])

    def test_powerscore_manual_on_league_edit(self):
        ensure_default_hitos(self.league)
        resolve_player("Ana", league=self.league)
        form = LeagueForm(
            data={
                "name": self.league.name,
                "description": "",
                "scoring_notes": "",
                "count_games": 8,
                "points_1st": 5,
                "points_2nd": 3,
                "points_3rd": 2,
                "points_4th": 1,
                "early_win_max_round": 6,
                "vp_thresholds": "10, 12, 15",
                "powerscore_value": "Dominó la mesa",
                "powerscore_players": ["Ana"],
            },
            instance=self.league,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        ps = powerscore_hito(self.league)
        self.assertEqual(ps.manual_value, "Dominó la mesa")
        self.assertEqual(ps.manual_player.name, "Ana")
        self.assertEqual(
            list(ps.manual_players.values_list("name", flat=True)), ["Ana"]
        )
        snap = next(
            s for s in league_hito_snapshots(self.league) if s["hito"].slug == "powerscore"
        )
        self.assertFalse(snap["empty"])
        self.assertEqual(snap["value_label"], "Dominó la mesa")
        self.assertEqual(snap["holders"][0]["player_name"], "Ana")

    def test_powerscore_tie_multiple_players(self):
        ensure_default_hitos(self.league)
        resolve_player("Ana", league=self.league)
        resolve_player("Bob", league=self.league)
        form = LeagueForm(
            data={
                "name": self.league.name,
                "description": "",
                "scoring_notes": "",
                "count_games": 8,
                "points_1st": 5,
                "points_2nd": 3,
                "points_3rd": 2,
                "points_4th": 1,
                "early_win_max_round": 6,
                "vp_thresholds": "10, 12, 15",
                "powerscore_value": "Empate histórico",
                "powerscore_players": ["Ana", "Bob"],
            },
            instance=self.league,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        ps = powerscore_hito(self.league)
        self.assertEqual(
            set(ps.manual_players.values_list("name", flat=True)), {"Ana", "Bob"}
        )
        self.assertEqual(ps.manual_player.name, "Ana")
        snap = next(
            s for s in league_hito_snapshots(self.league) if s["hito"].slug == "powerscore"
        )
        holder_names = {h["player_name"] for h in snap["holders"]}
        self.assertEqual(holder_names, {"Ana", "Bob"})

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
