from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from games.admin_helpers.mixins import GuardedDeleteMixin
from games.services.delete_guards import (
    LeagueMembershipInlineFormSet,
    ensure_league_can_delete,
    ensure_player_can_delete,
)
from .models import Game, GameResult, League, LeagueHito, LeagueMembership, Player


class UsernameOnlyUserAdmin(BaseUserAdmin):
    """Auth users: username + password; email hidden and not required."""

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )


admin.site.unregister(User)
admin.site.register(User, UsernameOnlyUserAdmin)


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
    formset = LeagueMembershipInlineFormSet


class LeagueHitoInline(admin.TabularInline):
    model = LeagueHito
    extra = 0
    fields = (
        "slug",
        "name",
        "metric",
        "manual_value",
        "manual_players",
        "manual_player",
        "order",
        "is_active",
    )
    autocomplete_fields = ["manual_player", "manual_players"]
    filter_horizontal = ["manual_players"]


@admin.register(Player)
class PlayerAdmin(GuardedDeleteMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}

    def check_delete(self, obj):
        ensure_player_can_delete(obj)


@admin.register(LeagueHito)
class LeagueHitoAdmin(admin.ModelAdmin):
    list_display = ("name", "league", "slug", "metric", "order", "is_active")
    list_filter = ("league", "metric", "is_builtin", "is_active")
    search_fields = ("name", "slug", "league__name")


@admin.register(League)
class LeagueAdmin(GuardedDeleteMixin, admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    inlines = [LeagueMembershipInline, LeagueHitoInline]

    def check_delete(self, obj):
        ensure_league_can_delete(obj)


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
