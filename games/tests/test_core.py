from datetime import date, timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from games.forms import GameAllianceForm, LeagueForm
from games.services.hitos import ensure_default_hitos
from games.models import Game, GameResult, League, Player, resolve_player
from games.views import _apply_alliances
from games.services.scoring import (
    compute_league_points,
    compute_league_points_breakdown,
    config_from_form_data,
    default_scoring_config,
    game_score_summary,
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

    def test_game_score_summary_lists_all_players(self):
        self._result("A", 12, leader="Paul")
        self._result("B", 8)
        rows = game_score_summary(self.game, self.league)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["player_name"], "A")
        self.assertEqual(rows[0]["placement"], 1)
        self.assertEqual(rows[0]["victory_points"], 12)
        self.assertEqual(rows[0]["leader"], "Paul")
        self.assertEqual(
            rows[0]["result"].pk,
            self.game.results.get(player__name="A").pk,
        )
        self.assertEqual(rows[0]["total"], rows[0]["league_points"])
        self.assertGreater(rows[0]["league_points"], 0)
        self.assertIn("=", rows[0]["formula"])

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
                "_vp_thresholds_parsed": [10, 15],
            }
        )
        self.assertEqual(cfg["count_games"], 5)
        self.assertEqual(cfg["placement_points"][1], 4)
        self.assertEqual(cfg["vp_thresholds"], [10, 15])

    def test_parse_vp_thresholds_input(self):
        from games.services.scoring import parse_vp_thresholds_input

        self.assertEqual(parse_vp_thresholds_input("10, 12, 15"), [10, 12, 15])
        self.assertEqual(parse_vp_thresholds_input("15 10"), [10, 15])
        self.assertEqual(parse_vp_thresholds_input(""), [])

    def test_league_form_rejects_invalid_vp_thresholds(self):
        form = LeagueForm(
            data={
                "name": "Bad",
                "description": "",
                "scoring_notes": "",
                "count_games": 8,
                "points_1st": 5,
                "points_2nd": 3,
                "points_3rd": 2,
                "points_4th": 1,
                "early_win_max_round": 6,
                "vp_thresholds": "10, foo, 15",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ERROR", form.errors["vp_thresholds"][0])

    def test_league_form_custom_vp_thresholds(self):
        form = LeagueForm(
            data={
                "name": "Umbrales",
                "description": "",
                "scoring_notes": "",
                "count_games": 8,
                "points_1st": 5,
                "points_2nd": 3,
                "points_3rd": 2,
                "points_4th": 1,
                "early_win_max_round": 6,
                "vp_thresholds": "8, 11, 14",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        league = form.save()
        self.assertEqual(
            resolve_scoring_config(league)["vp_thresholds"], [8, 11, 14]
        )

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
        self.assertContains(
            response,
            f'value="{self.game.played_on.isoformat()}"',
            msg_prefix="Date field should be pre-filled for HTML5 date input",
        )

    def test_edit_saves_alliances(self):
        results = list(self.game.results.order_by("pk"))
        results[0].alliance_emperor = True
        results[0].save(update_fields=["alliance_emperor"])
        url = reverse("games:edit", kwargs={"pk": self.game.pk})
        get_response = self.client.get(url)
        data = {
            "league": str(self.league.pk),
            "played_on": self.game.played_on.isoformat(),
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
            "results-0-victory_points": "10",
            "results-0-sardaukar_count": "0",
            "results-1-id": str(results[1].pk),
            "results-1-player_pick": "Bob",
            "results-1-leader": "",
            "results-1-victory_points": "8",
            "results-1-sardaukar_count": "0",
            "alliance_emperor": "Bob",
            "alliance_guild": "Bob",
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
        ana = GameResult.objects.get(game=self.game, player__name="Ana")
        bob = GameResult.objects.get(game=self.game, player__name="Bob")
        self.assertFalse(ana.alliance_emperor)
        self.assertTrue(bob.alliance_emperor)
        self.assertTrue(bob.alliance_guild)

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


class GameWinnerTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Liga", slug="liga-w")
        self.game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        self.ana = resolve_player("Ana", league=self.league)
        self.bob = resolve_player("Bob", league=self.league)
        self.r_ana = GameResult.objects.create(
            game=self.game, player=self.ana, victory_points=10
        )
        self.r_bob = GameResult.objects.create(
            game=self.game, player=self.bob, victory_points=10
        )

    def test_vp_tie_without_designation_has_no_winner(self):
        self.game.designated_winner = None
        self.game.tied_game = False
        self.game.save()
        self.assertIsNone(self.game.resolved_winner())
        self.assertFalse(self.r_ana.is_winner)
        self.assertFalse(self.r_bob.is_winner)

    def test_designated_winner_breaks_tie(self):
        self.game.designated_winner = self.r_bob
        self.game.save()
        self.assertFalse(self.r_ana.is_winner)
        self.assertTrue(self.r_bob.is_winner)

    def test_designated_winner_gets_first_place_scoring(self):
        self.game.rounds = 5
        self.game.designated_winner = self.r_bob
        self.game.save()
        self.assertEqual(self.r_bob.placement, 1)
        self.assertEqual(self.r_ana.placement, 2)
        bob_pts = compute_league_points_breakdown(self.r_bob, self.league)
        ana_pts = compute_league_points_breakdown(self.r_ana, self.league)
        self.assertEqual(bob_pts["placement_points"], 5)
        self.assertEqual(ana_pts["placement_points"], 3)
        self.assertEqual(bob_pts["early_win"], 1)
        self.assertEqual(ana_pts["early_win"], 0)

    def test_unresolved_vp_tie_shares_first_place(self):
        self.assertEqual(self.r_ana.placement, 1)
        self.assertEqual(self.r_bob.placement, 1)
        ana_pts = compute_league_points_breakdown(self.r_ana, self.league)
        self.assertEqual(ana_pts["placement_points"], 5)

    def test_tied_game_flag(self):
        self.game.tied_game = True
        self.game.designated_winner = None
        self.game.save()
        self.assertIsNone(self.game.resolved_winner())
        self.assertIn("Empate", self.game.winner_summary)


class ApplyAlliancesTests(TestCase):
    def test_apply_alliances_moves_holder(self):
        league = League.objects.create(name="L", slug="apply-l")
        game = Game.objects.create(
            league=league, played_on=date.today(), player_count=2
        )
        ana = resolve_player("Ana", league=league)
        bob = resolve_player("Bob", league=league)
        r_ana = GameResult.objects.create(
            game=game, player=ana, victory_points=10, alliance_emperor=True
        )
        r_bob = GameResult.objects.create(
            game=game, player=bob, victory_points=8
        )
        _apply_alliances(
            [r_ana, r_bob],
            {
                "alliance_emperor": "Bob",
                "alliance_guild": "Bob",
                "alliance_bene_gesserit": "",
                "alliance_fremen": "",
            },
        )
        r_ana.refresh_from_db()
        r_bob.refresh_from_db()
        self.assertFalse(r_ana.alliance_emperor)
        self.assertTrue(r_bob.alliance_emperor)
        self.assertTrue(r_bob.alliance_guild)


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


STORAGES_OVERRIDE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=STORAGES_OVERRIDE)
class LeagueGamesSortTests(TestCase):
    def test_league_detail_games_sort_newest_and_oldest(self):
        league = League.objects.create(name="Sort Liga", slug="sort-liga")
        old = Game.objects.create(
            league=league, played_on=date(2024, 1, 1), player_count=2
        )
        new = Game.objects.create(
            league=league, played_on=date(2025, 6, 1), player_count=2
        )
        client = Client()
        url = reverse("games:league_detail", kwargs={"slug": league.slug})

        newest = client.get(url)
        self.assertEqual(newest.status_code, 200)
        ids = [e["game"].pk for e in newest.context["game_entries"]]
        self.assertEqual(ids, [new.pk, old.pk])

        oldest = client.get(url, {"sort": "oldest"})
        self.assertEqual(oldest.context["games_sort"], "oldest")
        ids_old = [e["game"].pk for e in oldest.context["game_entries"]]
        self.assertEqual(ids_old, [old.pk, new.pk])

    def test_league_fecha_numbers_fixed_across_sort(self):
        league = League.objects.create(name="Fecha Liga", slug="fecha-liga")
        old = Game.objects.create(
            league=league, played_on=date(2024, 1, 1), player_count=2
        )
        new = Game.objects.create(
            league=league, played_on=date(2025, 6, 1), player_count=2
        )
        client = Client()
        url = reverse("games:league_detail", kwargs={"slug": league.slug})

        newest = client.get(url)
        fechas_newest = {e["game"].pk: e["fecha_number"] for e in newest.context["game_entries"]}
        self.assertEqual(fechas_newest[old.pk], 1)
        self.assertEqual(fechas_newest[new.pk], 2)

        oldest = client.get(url, {"sort": "oldest"})
        fechas_oldest = {e["game"].pk: e["fecha_number"] for e in oldest.context["game_entries"]}
        self.assertEqual(fechas_oldest, fechas_newest)

    def test_league_detail_shows_fecha_title_and_extras(self):
        league = League.objects.create(name="Extras Liga", slug="extras-liga")
        game = Game.objects.create(
            league=league, played_on=date.today(), player_count=2
        )
        p1 = resolve_player("Kori", league=league)
        p2 = resolve_player("Alex", league=league)
        GameResult.objects.create(
            game=game,
            player=p1,
            victory_points=10,
            sardaukar_count=2,
            alliance_emperor=True,
            order=0,
        )
        GameResult.objects.create(
            game=game, player=p2, victory_points=5, order=1
        )
        response = Client().get(
            reverse("games:league_detail", kwargs={"slug": league.slug})
        )
        self.assertContains(response, "Fecha N°1")
        self.assertContains(response, "results-table")
        self.assertContains(response, "2 Sardaukars")
        self.assertContains(response, "Emperador")
        self.assertContains(response, "Pts. liga")
        self.assertNotContains(response, 'class="league-game-card__date"')
        self.assertNotContains(response, "game-player-scores")


@override_settings(STORAGES=STORAGES_OVERRIDE)
class LeagueGamesPaginationTests(TestCase):
    def test_league_detail_paginates_games(self):
        league = League.objects.create(name="Page Liga", slug="page-liga")
        created = []
        for day in range(1, 22):
            created.append(
                Game.objects.create(
                    league=league,
                    played_on=date(2024, 1, day),
                    player_count=2,
                )
            )
        client = Client()
        url = reverse("games:league_detail", kwargs={"slug": league.slug})

        page1 = client.get(url, {"sort": "newest"})
        self.assertEqual(page1.status_code, 200)
        self.assertEqual(len(page1.context["game_entries"]), 20)
        self.assertTrue(page1.context["games_page"].has_next())
        self.assertContains(page1, "Página 1 de 2")

        page2 = client.get(url, {"sort": "newest", "page": 2})
        self.assertEqual(len(page2.context["game_entries"]), 1)
        self.assertEqual(page2.context["game_entries"][0]["game"].pk, created[0].pk)

    def test_league_game_url_includes_page_for_deep_game(self):
        from games.views import _league_game_url

        league = League.objects.create(name="Deep Liga", slug="deep-liga")
        games = []
        for day in range(1, 22):
            games.append(
                Game.objects.create(
                    league=league,
                    played_on=date(2024, 1, day),
                    player_count=2,
                )
            )
        oldest = games[0]
        url = _league_game_url(oldest, return_sort="newest")
        self.assertIn("page=2", url)
        self.assertIn(f"#game-{oldest.pk}", url)


@override_settings(STORAGES=STORAGES_OVERRIDE)
class LeagueRosterEditTests(TestCase):
    def _league_edit_post_data(self, league, **overrides):
        data = {
            "name": league.name,
            "description": "",
            "scoring_notes": "",
            "count_games": 8,
            "points_1st": 5,
            "points_2nd": 3,
            "points_3rd": 2,
            "points_4th": 1,
            "early_win_max_round": 6,
            "vp_thresholds": "10, 12, 15",
            "powerscore_value": "",
        }
        data.update(overrides)
        return data

    def test_league_edit_save_via_guardar_liga(self):
        league = League.objects.create(name="Save Liga", slug="save-liga")
        ensure_default_hitos(league)
        client = Client()
        url = reverse("games:league_edit", kwargs={"slug": league.slug})
        response = client.post(
            url,
            self._league_edit_post_data(league, name="Save Liga Updated"),
        )
        self.assertRedirects(
            response,
            reverse("games:league_detail", kwargs={"slug": league.slug}),
        )
        league.refresh_from_db()
        self.assertEqual(league.name, "Save Liga Updated")

    def test_league_edit_roster_forms_outside_main_form(self):
        league = League.objects.create(name="Nested Liga", slug="nested-liga")
        ensure_default_hitos(league)
        resolve_player("Ana", league=league)
        response = Client().get(
            reverse("games:league_edit", kwargs={"slug": league.slug})
        )
        html = response.content.decode()
        main_end = html.index("</form>")
        self.assertIn("Guardar liga", html[:main_end])
        self.assertIn("Plantel", html[main_end:])
        self.assertNotIn("<form", html[:main_end].replace('<form method="post" class="game-form">', "", 1))

    def test_roster_on_edit_not_on_detail(self):
        league = League.objects.create(name="Roster Liga", slug="roster-liga")
        player = resolve_player("Ana", league=league)
        client = Client()

        detail = client.get(reverse("games:league_detail", kwargs={"slug": league.slug}))
        self.assertNotContains(detail, "Añadir jugador")
        self.assertNotContains(detail, "Plantel")

        edit = client.get(reverse("games:league_edit", kwargs={"slug": league.slug}))
        self.assertContains(edit, "Plantel")
        self.assertContains(edit, "Ana")
        self.assertContains(edit, "Añadir jugador")

        add = client.post(
            reverse("games:league_add_player", kwargs={"slug": league.slug}),
            {"name": "Bob"},
        )
        self.assertRedirects(
            add,
            reverse("games:league_edit", kwargs={"slug": league.slug}),
        )
        self.assertTrue(
            league.players.filter(name="Bob").exists()
        )

        remove = client.post(
            reverse(
                "games:league_remove_player",
                kwargs={"slug": league.slug, "player_id": player.pk},
            ),
        )
        self.assertRedirects(
            remove,
            reverse("games:league_edit", kwargs={"slug": league.slug}),
        )
        self.assertFalse(league.players.filter(pk=player.pk).exists())

    def test_roster_remove_blocked_when_player_has_league_games(self):
        league = League.objects.create(name="Guard Liga", slug="guard-liga")
        player = resolve_player("Ana", league=league)
        game = Game.objects.create(
            league=league,
            played_on=date.today(),
            player_count=2,
        )
        GameResult.objects.create(
            game=game,
            player=player,
            victory_points=10,
        )
        client = Client()
        response = client.post(
            reverse(
                "games:league_remove_player",
                kwargs={"slug": league.slug, "player_id": player.pk},
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(league.players.filter(pk=player.pk).exists())
