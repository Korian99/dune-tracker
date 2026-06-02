from django.contrib import admin

from .models import Game, GameResult, League


class GameResultInline(admin.TabularInline):
    model = GameResult
    extra = 2
    fields = (
        "player_name",
        "leader",
        "victory_points",
        "sardaukar_count",
        "alliance_emperor",
        "alliance_guild",
        "alliance_bene_gesserit",
        "alliance_fremen",
    )


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)


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
        "player_name",
        "leader",
        "victory_points",
        "sardaukar_count",
    )
