from datetime import date

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Game, GameResult, League, resolve_player
from .tiebreak import (
    apply_tiebreak,
    game_needs_tiebreak,
    has_top_vp_tie,
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

    def test_apply_winner_and_tie(self):
        leaders = self.game.max_vp_results()
        apply_tiebreak(self.game, "winner", str(leaders[0].pk))
        self.game.refresh_from_db()
        self.assertFalse(self.game.tied_game)
        self.assertTrue(leaders[0].is_winner)

        apply_tiebreak(self.game, "tie", None)
        self.game.refresh_from_db()
        self.assertTrue(self.game.tied_game)
        self.assertIsNone(self.game.resolved_winner())


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
                "resolution": "winner",
                "winner_result_id": str(r2.pk),
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
        self.assertContains(page, "importada")
