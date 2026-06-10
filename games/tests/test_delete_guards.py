from datetime import date

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from games.admin import LeagueAdmin
from games.services.delete_guards import (
    ensure_league_can_delete,
    ensure_league_roster_can_remove,
    ensure_player_can_delete,
)
from games.models import Game, GameResult, League, LeagueMembership, Player, resolve_player


class DeleteGuardTests(TestCase):
    def setUp(self):
        self.league = League.objects.create(name="Liga", slug="liga-guard")
        self.player = resolve_player("Ana", league=self.league)

    def test_league_without_games_can_delete(self):
        ensure_league_can_delete(self.league)

    def test_league_with_games_cannot_delete(self):
        Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        with self.assertRaises(ValidationError):
            ensure_league_can_delete(self.league)

    def test_player_without_games_can_delete(self):
        solo = Player.objects.create(name="Solo")
        ensure_player_can_delete(solo)

    def test_player_with_results_cannot_delete(self):
        game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        GameResult.objects.create(
            game=game,
            player=self.player,
            victory_points=10,
        )
        with self.assertRaises(ValidationError):
            ensure_player_can_delete(self.player)

    def test_roster_remove_without_league_games(self):
        extra = resolve_player("Bob", league=self.league)
        LeagueMembership.objects.filter(league=self.league, player=extra).delete()
        ensure_league_roster_can_remove(self.league, extra)

    def test_roster_remove_with_league_games_blocked(self):
        game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        GameResult.objects.create(
            game=game,
            player=self.player,
            victory_points=10,
        )
        with self.assertRaises(ValidationError):
            ensure_league_roster_can_remove(self.league, self.player)

    def test_league_remove_player_view_blocks_when_games_exist(self):
        game = Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        GameResult.objects.create(
            game=game,
            player=self.player,
            victory_points=10,
        )
        url = reverse(
            "games:league_remove_player",
            kwargs={"slug": self.league.slug, "player_id": self.player.pk},
        )
        response = Client().post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("games:league_edit", kwargs={"slug": self.league.slug}),
        )
        self.assertTrue(self.league.players.filter(pk=self.player.pk).exists())

    def test_league_admin_has_no_delete_when_games_exist(self):
        Game.objects.create(
            league=self.league,
            played_on=date.today(),
            player_count=2,
        )
        site = AdminSite()
        admin = LeagueAdmin(League, site)
        request = type("R", (), {"user": None})()
        self.assertFalse(admin.has_delete_permission(request, self.league))
