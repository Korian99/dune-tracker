from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from games.models import Game, GameResult, League, resolve_player
from games.services.scoring import compute_league_points_breakdown
from games.services.tiebreak import (
    apply_tiebreak,
    apply_tiebreaks_from_post,
    game_needs_tiebreak,
    has_top_vp_tie,
    has_vp_ties,
    placements_for_game,
    selected_tiebreak_for_group,
    vp_tie_groups,
)

STORAGES_OVERRIDE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


class TiebreakLogicTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="L", slug="tie-l")
        self.game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=3
        )
        for name, vp in [("A", 12), ("B", 12), ("C", 8), ("D", 8)]:
            GameResult.objects.create(
                game=self.game,
                player=resolve_player(name, league=self.league),
                victory_points=vp,
            )

    def test_vp_tie_groups_finds_winner_and_other(self):
        groups = vp_tie_groups(self.game)
        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[0]["is_winner_group"])
        self.assertEqual(groups[0]["vp"], 12)
        self.assertEqual(len(groups[0]["results"]), 2)
        self.assertFalse(groups[1]["is_winner_group"])
        self.assertEqual(groups[1]["vp"], 8)

    def test_needs_tiebreak_when_top_shared(self):
        self.assertTrue(game_needs_tiebreak(self.game))

    def test_lower_vp_tie_needs_resolution(self):
        self.assertTrue(has_vp_ties(self.game))
        by_name = {r.player.name: r for r in self.game.results.select_related("player")}
        apply_tiebreak(self.game, "winner", str(by_name["A"].pk))
        self.game.refresh_from_db()
        self.assertTrue(game_needs_tiebreak(self.game))

    def test_all_placements_after_full_tiebreak(self):
        by_name = {r.player.name: r for r in self.game.results.select_related("player")}
        apply_tiebreak(self.game, "winner", str(by_name["A"].pk))
        apply_tiebreak(self.game, "winner", str(by_name["C"].pk), vp=8)
        self.game.refresh_from_db()
        self.assertFalse(game_needs_tiebreak(self.game))
        self.assertEqual(by_name["A"].placement, 1)
        self.assertEqual(by_name["B"].placement, 2)
        self.assertEqual(by_name["C"].placement, 3)
        self.assertEqual(by_name["D"].placement, 4)
        self.assertEqual(
            compute_league_points_breakdown(by_name["C"], self.league)["placement_points"],
            2,
        )
        self.assertEqual(
            compute_league_points_breakdown(by_name["D"], self.league)["placement_points"],
            1,
        )

    def test_three_way_top_vp_full_order(self):
        """3-way tie at top: assign 1st, 2nd, 3rd within group."""
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=3
        )
        players = [
            resolve_player(n, league=self.league) for n in ("A", "B", "C")
        ]
        results = [
            GameResult.objects.create(game=game, player=p, victory_points=12)
            for p in players
        ]
        by_pk = {r.player.name: r for r in results}
        apply_tiebreak(
            game,
            "rank",
            order_result_ids=[by_pk["B"].pk, by_pk["A"].pk, by_pk["C"].pk],
            vp=12,
        )
        game.refresh_from_db()
        self.assertFalse(game_needs_tiebreak(game))
        self.assertEqual(by_pk["B"].placement, 1)
        self.assertEqual(by_pk["A"].placement, 2)
        self.assertEqual(by_pk["C"].placement, 3)
        self.assertTrue(by_pk["B"].is_winner)
        self.assertEqual(
            compute_league_points_breakdown(by_pk["B"], self.league)[
                "placement_points"
            ],
            5,
        )
        self.assertEqual(
            compute_league_points_breakdown(by_pk["A"], self.league)[
                "placement_points"
            ],
            3,
        )
        self.assertEqual(
            compute_league_points_breakdown(by_pk["C"], self.league)[
                "placement_points"
            ],
            2,
        )

    def test_apply_winner_and_tie(self):
        leaders = self.game.max_vp_results()
        apply_tiebreak(self.game, "winner", str(leaders[0].pk))
        self.game.refresh_from_db()
        self.assertFalse(self.game.tied_game)
        self.assertTrue(leaders[0].is_winner)
        loser = leaders[1]
        self.assertEqual(leaders[0].placement, 1)
        self.assertEqual(loser.placement, 2)
        self.assertEqual(
            compute_league_points_breakdown(leaders[0], self.league)[
                "placement_points"
            ],
            5,
        )
        self.assertEqual(
            compute_league_points_breakdown(loser, self.league)["placement_points"],
            3,
        )

        apply_tiebreak(self.game, "tie", None)
        self.game.refresh_from_db()
        self.assertTrue(self.game.tied_game)
        self.assertIsNone(self.game.resolved_winner())

    def test_four_way_top_vp_full_order(self):
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=4
        )
        names = ("A", "B", "C", "D")
        results = [
            GameResult.objects.create(
                game=game,
                player=resolve_player(n, league=self.league),
                victory_points=11,
            )
            for n in names
        ]
        by_name = {r.player.name: r for r in results}
        apply_tiebreak(
            game,
            "rank",
            order_result_ids=[
                by_name["D"].pk,
                by_name["A"].pk,
                by_name["C"].pk,
                by_name["B"].pk,
            ],
            vp=11,
        )
        game.refresh_from_db()
        self.assertEqual(by_name["D"].placement, 1)
        self.assertEqual(by_name["A"].placement, 2)
        self.assertEqual(by_name["C"].placement, 3)
        self.assertEqual(by_name["B"].placement, 4)
        self.assertEqual(
            compute_league_points_breakdown(by_name["B"], self.league)[
                "placement_points"
            ],
            1,
        )

    def test_three_way_same_placement_tie_scoring(self):
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=3
        )
        results = [
            GameResult.objects.create(
                game=game,
                player=resolve_player(n, league=self.league),
                victory_points=12,
            )
            for n in ("A", "B", "C")
        ]
        apply_tiebreak(game, "tie", vp=12)
        game.refresh_from_db()
        for r in results:
            r.refresh_from_db()
            self.assertEqual(r.placement, 1)
            self.assertEqual(
                compute_league_points_breakdown(r, self.league)["placement_points"],
                5,
            )

    def test_lower_vp_three_way_rank(self):
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=4
        )
        by_name = {}
        for name, vp in [("A", 12), ("B", 8), ("C", 8), ("D", 8)]:
            by_name[name] = GameResult.objects.create(
                game=game,
                player=resolve_player(name, league=self.league),
                victory_points=vp,
            )
        apply_tiebreak(
            game,
            "rank",
            order_result_ids=[
                by_name["D"].pk,
                by_name["C"].pk,
                by_name["B"].pk,
            ],
            vp=8,
        )
        game.refresh_from_db()
        self.assertFalse(game_needs_tiebreak(game))
        self.assertEqual(by_name["A"].placement, 1)
        self.assertEqual(by_name["D"].placement, 2)
        self.assertEqual(by_name["C"].placement, 3)
        self.assertEqual(by_name["B"].placement, 4)

    def test_apply_tiebreaks_from_post_rank_three_way(self):
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=3
        )
        results = [
            GameResult.objects.create(
                game=game,
                player=resolve_player(n, league=self.league),
                victory_points=10,
            )
            for n in ("X", "Y", "Z")
        ]
        by_name = {r.player.name: r for r in results}
        post = {
            f"tiebreak_10_resolution": "rank",
            f"tiebreak_10_rank_{by_name['Y'].pk}": "1",
            f"tiebreak_10_rank_{by_name['Z'].pk}": "2",
            f"tiebreak_10_rank_{by_name['X'].pk}": "3",
        }
        apply_tiebreaks_from_post(game, post)
        game.refresh_from_db()
        self.assertFalse(game_needs_tiebreak(game))
        self.assertEqual(by_name["Y"].placement, 1)
        self.assertEqual(by_name["Z"].placement, 2)
        self.assertEqual(by_name["X"].placement, 3)
        self.assertEqual(game.placement_tiebreaks["10"], [by_name["Y"].pk, by_name["Z"].pk, by_name["X"].pk])

    def test_apply_tiebreaks_from_post_rejects_duplicate_ranks(self):
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=3
        )
        results = [
            GameResult.objects.create(
                game=game,
                player=resolve_player(n, league=self.league),
                victory_points=10,
            )
            for n in ("P", "Q", "R")
        ]
        post = {
            "tiebreak_10_resolution": "rank",
            f"tiebreak_10_rank_{results[0].pk}": "1",
            f"tiebreak_10_rank_{results[1].pk}": "1",
            f"tiebreak_10_rank_{results[2].pk}": "2",
        }
        with self.assertRaises(ValueError) as ctx:
            apply_tiebreaks_from_post(game, post)
        self.assertIn("sin repetir", str(ctx.exception))

    def test_selected_tiebreak_reflects_stored_order(self):
        game = Game.objects.create(
            league=self.league, played_on=date.today(), player_count=3
        )
        results = [
            GameResult.objects.create(
                game=game,
                player=resolve_player(n, league=self.league),
                victory_points=9,
            )
            for n in ("M", "N", "O")
        ]
        order = [results[1].pk, results[0].pk, results[2].pk]
        apply_tiebreak(game, "rank", order_result_ids=order, vp=9)
        game.refresh_from_db()
        group = vp_tie_groups(game)[0]
        state = selected_tiebreak_for_group(game, group)
        self.assertEqual(state["resolution"], "rank")
        self.assertEqual(state["ranks"][results[1].pk], 1)
        self.assertEqual(state["ranks"][results[0].pk], 2)
        self.assertEqual(state["ranks"][results[2].pk], 3)

    def test_rank_both_groups_via_post(self):
        by_name = {r.player.name: r for r in self.game.results.select_related("player")}
        post = {
            "tiebreak_12_resolution": "rank",
            f"tiebreak_12_rank_{by_name['A'].pk}": "2",
            f"tiebreak_12_rank_{by_name['B'].pk}": "1",
            "tiebreak_8_resolution": "rank",
            f"tiebreak_8_rank_{by_name['C'].pk}": "1",
            f"tiebreak_8_rank_{by_name['D'].pk}": "2",
        }
        apply_tiebreaks_from_post(self.game, post)
        self.game.refresh_from_db()
        self.assertFalse(game_needs_tiebreak(self.game))
        self.assertEqual(by_name["B"].placement, 1)
        self.assertEqual(by_name["A"].placement, 2)
        self.assertEqual(by_name["C"].placement, 3)
        self.assertEqual(by_name["D"].placement, 4)


@override_settings(STORAGES=STORAGES_OVERRIDE)
class TiebreakRedirectTests(TestCase):
    def test_save_with_tie_redirects_to_resolve_page(self):
        league = League.objects.create(name="L2", slug="tie-l2")
        game = Game.objects.create(
            league=league, played_on=date.today(), player_count=2
        )
        ana = resolve_player("Ana", league=league)
        bob = resolve_player("Bob", league=league)
        r1 = GameResult.objects.create(game=game, player=ana, victory_points=10)
        r2 = GameResult.objects.create(game=game, player=bob, victory_points=10)

        client = Client()
        url = reverse("games:edit", kwargs={"pk": game.pk})
        get = client.get(url)
        data = {
            "league": str(league.pk),
            "played_on": game.played_on.isoformat(),
            "player_count": "2",
            "duration_hours": "",
            "duration_minutes_part": "",
            "rounds": "",
            "notes": "",
            "results-TOTAL_FORMS": get.context["formset"].total_form_count(),
            "results-INITIAL_FORMS": get.context["formset"].initial_form_count(),
            "results-MIN_NUM_FORMS": "0",
            "results-MAX_NUM_FORMS": "6",
            "results-0-id": str(r1.pk),
            "results-0-player_pick": "Ana",
            "results-0-leader": "",
            "results-0-victory_points": "10",
            "results-0-sardaukar_count": "0",
            "results-1-id": str(r2.pk),
            "results-1-player_pick": "Bob",
            "results-1-leader": "",
            "results-1-victory_points": "10",
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

        response = client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("games:resolve_tie", kwargs={"pk": game.pk})
        )
        resolve_url = reverse("games:resolve_tie", kwargs={"pk": game.pk})
        pick = client.post(
            resolve_url,
            {
                "tiebreak_10_resolution": "rank",
                "tiebreak_10_rank_" + str(r2.pk): "1",
                "tiebreak_10_rank_" + str(r1.pk): "2",
            },
        )
        self.assertEqual(pick.status_code, 302)
        r2.refresh_from_db()
        self.assertTrue(r2.is_winner)

    def test_imported_style_tie_redirects_after_edit_save(self):
        """Backfilled designated_winner still goes to tiebreak on edit+save."""
        league = League.objects.create(name="Imp", slug="imp-l")
        game = Game.objects.create(
            league=league, played_on=date.today(), player_count=2
        )
        ana = resolve_player("Ana", league=league)
        bob = resolve_player("Bob", league=league)
        r1 = GameResult.objects.create(game=game, player=ana, victory_points=10)
        r2 = GameResult.objects.create(game=game, player=bob, victory_points=10)
        game.designated_winner = r1
        game.save(update_fields=["designated_winner"])
        self.assertFalse(game_needs_tiebreak(game))
        self.assertTrue(has_top_vp_tie(game))

        client = Client()
        url = reverse("games:edit", kwargs={"pk": game.pk})
        get = client.get(url)
        data = {
            "league": str(league.pk),
            "played_on": game.played_on.isoformat(),
            "player_count": "2",
            "duration_hours": "",
            "duration_minutes_part": "",
            "rounds": "",
            "notes": "",
            "results-TOTAL_FORMS": get.context["formset"].total_form_count(),
            "results-INITIAL_FORMS": get.context["formset"].initial_form_count(),
            "results-MIN_NUM_FORMS": "0",
            "results-MAX_NUM_FORMS": "6",
            "results-0-id": str(r1.pk),
            "results-0-player_pick": "Ana",
            "results-0-leader": "",
            "results-0-victory_points": "10",
            "results-0-sardaukar_count": "0",
            "results-1-id": str(r2.pk),
            "results-1-player_pick": "Bob",
            "results-1-leader": "",
            "results-1-victory_points": "10",
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

        response = client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("games:resolve_tie", kwargs={"pk": game.pk})
        )

        page = client.get(reverse("games:resolve_tie", kwargs={"pk": game.pk}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "desempates guardados")
