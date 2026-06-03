from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
    path("", views.home, name="home"),
    path("games/", views.game_list, name="list"),
    path("games/new/", views.game_create, name="create"),
    path("games/<int:pk>/", views.game_detail, name="detail"),
    path("games/<int:pk>/edit/", views.game_edit, name="edit"),
    path("games/<int:pk>/delete/", views.game_delete, name="delete"),
    path("stats/", views.stats, name="stats"),
    path("leagues/", views.league_list, name="league_list"),
    path("leagues/new/", views.league_create, name="league_create"),
    path("leagues/<slug:slug>/", views.league_detail, name="league_detail"),
    path(
        "leagues/<slug:slug>/export/",
        views.league_sheet_export,
        name="league_sheet_export",
    ),
    path("leagues/<slug:slug>/edit/", views.league_edit, name="league_edit"),
    path(
        "leagues/<slug:slug>/players/add/",
        views.league_add_player,
        name="league_add_player",
    ),
]
