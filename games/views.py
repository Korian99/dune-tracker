from collections import Counter
from datetime import date

from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import GameForm, GameResultFormSet, LEADER_SUGGESTIONS, LeagueForm
from .models import Game, GameResult, League
from .scoring import league_standings


def _save_results(formset):
    results = formset.save()
    for i, result in enumerate(results):
        if result.order != i:
            result.order = i
            result.save(update_fields=["order"])


def _games_queryset(league_slug=None):
    qs = Game.objects.select_related("league").prefetch_related("results")
    if league_slug:
        qs = qs.filter(league__slug=league_slug)
    return qs


def home(request):
    recent = _games_queryset()[:8]
    total_games = Game.objects.count()
    leagues = League.objects.all()[:6]
    return render(
        request,
        "games/home.html",
        {
            "recent_games": recent,
            "total_games": total_games,
            "leagues": leagues,
        },
    )


def game_list(request):
    league_slug = request.GET.get("league")
    games = _games_queryset(league_slug)
    leagues = League.objects.all()
    current_league = None
    if league_slug:
        current_league = get_object_or_404(League, slug=league_slug)
    return render(
        request,
        "games/game_list.html",
        {
            "games": games,
            "leagues": leagues,
            "current_league": current_league,
        },
    )


def game_detail(request, pk):
    game = get_object_or_404(
        Game.objects.select_related("league").prefetch_related("results"),
        pk=pk,
    )
    alliance_map = _alliance_map_for_game(game)
    return render(
        request,
        "games/game_detail.html",
        {"game": game, "alliance_map": alliance_map},
    )


def _alliance_map_for_game(game):
    """Faction label -> player name for alliances held in this game."""
    mapping = {}
    for result in game.results.all():
        for field, label in GameResult.ALLIANCE_FIELDS:
            if getattr(result, field):
                mapping[label] = result.player_name
    return mapping


@require_http_methods(["GET", "POST"])
def game_create(request):
    league_slug = request.GET.get("league")
    initial_league = None
    if league_slug:
        initial_league = League.objects.filter(slug=league_slug).first()

    if request.method == "POST":
        form = GameForm(request.POST)
        formset = GameResultFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            game = form.save()
            formset.instance = game
            _save_results(formset)
            return redirect("games:detail", pk=game.pk)
    else:
        initial = {"played_on": date.today(), "bloodlines": True}
        if initial_league:
            initial["league"] = initial_league
        form = GameForm(initial=initial)
        formset = GameResultFormSet()

    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "leader_suggestions": LEADER_SUGGESTIONS,
            "alliance_fields": GameResult.ALLIANCE_FIELDS,
            "is_edit": False,
        },
    )


@require_http_methods(["GET", "POST"])
def game_edit(request, pk):
    game = get_object_or_404(Game, pk=pk)
    if request.method == "POST":
        form = GameForm(request.POST, instance=game)
        formset = GameResultFormSet(request.POST, instance=game)
        if form.is_valid() and formset.is_valid():
            form.save()
            _save_results(formset)
            return redirect("games:detail", pk=game.pk)
    else:
        form = GameForm(instance=game)
        formset = GameResultFormSet(instance=game)

    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "leader_suggestions": LEADER_SUGGESTIONS,
            "alliance_fields": GameResult.ALLIANCE_FIELDS,
            "is_edit": True,
            "game": game,
        },
    )


@require_http_methods(["POST"])
def game_delete(request, pk):
    game = get_object_or_404(Game, pk=pk)
    game.delete()
    return redirect("games:list")


def stats(request):
    league_slug = request.GET.get("league")
    games_qs = Game.objects.all()
    if league_slug:
        games_qs = games_qs.filter(league__slug=league_slug)
        current_league = get_object_or_404(League, slug=league_slug)
    else:
        current_league = None

    results = GameResult.objects.filter(game__in=games_qs).select_related("game")
    player_wins = Counter()
    player_games = Counter()
    for r in results:
        player_games[r.player_name] += 1
        if r.is_winner:
            player_wins[r.player_name] += 1

    standings = []
    for name, games_played in player_games.most_common():
        wins = player_wins[name]
        avg_vp = results.filter(player_name=name).aggregate(avg=Avg("victory_points"))[
            "avg"
        ]
        avg_sard = results.filter(player_name=name).aggregate(
            avg=Avg("sardaukar_count")
        )["avg"]
        standings.append(
            {
                "name": name,
                "games": games_played,
                "wins": wins,
                "win_rate": round(100 * wins / games_played, 1) if games_played else 0,
                "avg_vp": round(avg_vp, 1) if avg_vp else 0,
                "avg_sardaukar": round(avg_sard, 1) if avg_sard else 0,
            }
        )
    standings.sort(key=lambda x: (-x["wins"], -x["avg_vp"]))

    leader_usage = (
        results.exclude(leader="")
        .values("leader")
        .annotate(times_played=Count("id"), avg_vp=Avg("victory_points"))
        .order_by("-times_played")[:12]
    )

    summary = games_qs.aggregate(
        total=Count("id"),
        with_bloodlines=Count("id", filter=Q(bloodlines=True)),
        avg_rounds=Avg("rounds"),
        avg_duration=Avg("duration_minutes"),
    )

    league_standings_rows = None
    if current_league:
        league_standings_rows = league_standings(current_league)

    return render(
        request,
        "games/stats.html",
        {
            "standings": standings,
            "leader_usage": leader_usage,
            "summary": summary,
            "leagues": League.objects.all(),
            "current_league": current_league,
            "league_standings": league_standings_rows,
        },
    )


def league_list(request):
    leagues = League.objects.annotate(game_count=Count("games"))
    return render(request, "games/league_list.html", {"leagues": leagues})


def league_detail(request, slug):
    league = get_object_or_404(League, slug=slug)
    games = league.games.prefetch_related("results")
    standings = league_standings(league)
    return render(
        request,
        "games/league_detail.html",
        {
            "league": league,
            "games": games,
            "standings": standings,
        },
    )


@require_http_methods(["GET", "POST"])
def league_create(request):
    if request.method == "POST":
        form = LeagueForm(request.POST)
        if form.is_valid():
            league = form.save()
            return redirect("games:league_detail", slug=league.slug)
    else:
        form = LeagueForm()
    return render(request, "games/league_form.html", {"form": form, "is_edit": False})


@require_http_methods(["GET", "POST"])
def league_edit(request, slug):
    league = get_object_or_404(League, slug=slug)
    if request.method == "POST":
        form = LeagueForm(request.POST, instance=league)
        if form.is_valid():
            form.save()
            return redirect("games:league_detail", slug=league.slug)
    else:
        form = LeagueForm(instance=league)
    return render(
        request,
        "games/league_form.html",
        {"form": form, "is_edit": True, "league": league},
    )
