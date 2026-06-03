from django.contrib import admin

from .models import Game, GameResult, League, LeagueMembership, Player


class GameResultInline(admin.TabularInline):
    model = GameResult
    extra = 2
    fields = (
        "player",
        "leader",
        "victory_points",
        "sardaukar_count",
        "alliance_emperor",
        "alliance_guild",
        "alliance_bene_gesserit",
        "alliance_fremen",
    )


class LeagueMembershipInline(admin.TabularInline):
    model = LeagueMembership
    extra = 1
    autocomplete_fields = ["player"]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    inlines = [LeagueMembershipInline]


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "played_on",
        "league",
        "base_game",
        "bloodlines",
        "rounds",
        "duration_minutes",
        "player_count",
    )
    list_filter = ("league", "base_game", "bloodlines", "player_count")
    inlines = [GameResultInline]


@admin.register(GameResult)
class GameResultAdmin(admin.ModelAdmin):
    list_display = (
        "game",
        "player",
        "leader",
        "victory_points",
        "sardaukar_count",
    )
