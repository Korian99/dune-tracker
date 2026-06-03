from collections import Counter
from datetime import date

from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import (
    GameForm,
    GameResultFormSet,
    LEADER_SUGGESTIONS,
    LeagueAddPlayerForm,
    LeagueForm,
)
from .models import Game, GameResult, League
from .scoring import (
    DEFAULT_SCORING_NOTES,
    breakdown_display,
    compute_league_points_breakdown,
    league_standings,
    resolve_scoring_config,
)


def _save_results(formset):
    results = formset.save()
    for i, result in enumerate(results):
        if result.order != i:
            result.order = i
            result.save(update_fields=["order"])


def _games_queryset(league_slug=None):
    qs = Game.objects.select_related("league").prefetch_related(
        "results__player"
    )
    if league_slug:
        qs = qs.filter(league__slug=league_slug)
    return qs


def _roster_names(league):
    if not league:
        return []
    return list(
        league.players.order_by("name").values_list("name", flat=True)
    )


def _formset_for_game(game=None, league=None, data=None):
    """Build result formset with league context for player resolution."""
    league = league or (game.league if game and game.league_id else None)
    kwargs = {"form_kwargs": {"league": league}}
    if game:
        kwargs["instance"] = game
    if data is not None:
        kwargs["data"] = data
    return GameResultFormSet(**kwargs)


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
        Game.objects.select_related("league").prefetch_related("results__player"),
        pk=pk,
    )
    alliance_map = _alliance_map_for_game(game)
    league_score_rows = None
    if game.league_id:
        league_score_rows = []
        for result in game.results.all():
            breakdown = compute_league_points_breakdown(result, game.league)
            league_score_rows.append(
                {
                    "result": result,
                    "breakdown": breakdown,
                    "formula": breakdown_display(breakdown),
                    "total": breakdown["total"],
                }
            )
    return render(
        request,
        "games/game_detail.html",
        {
            "game": game,
            "alliance_map": alliance_map,
            "league_score_rows": league_score_rows,
        },
    )


def _alliance_map_for_game(game):
    """Faction label -> player name for alliances held in this game."""
    mapping = {}
    for result in game.results.select_related("player"):
        for field, label in GameResult.ALLIANCE_FIELDS:
            if getattr(result, field):
                mapping[label] = result.player.name
    return mapping


@require_http_methods(["GET", "POST"])
def game_create(request):
    league_slug = request.GET.get("league")
    initial_league = None
    if league_slug:
        initial_league = League.objects.filter(slug=league_slug).first()

    if request.method == "POST":
        form = GameForm(request.POST)
        league_for_formset = (
            form.cleaned_data.get("league")
            if form.is_valid()
            else _league_from_form(form) or initial_league
        )
        formset = _formset_for_game(league=league_for_formset, data=request.POST)
        if form.is_valid() and formset.is_valid():
            game = form.save()
            formset.instance = game
            formset.league = game.league
            for f in formset.forms:
                f.league = game.league
            _save_results(formset)
            return redirect("games:detail", pk=game.pk)
    else:
        initial = {"played_on": date.today(), "bloodlines": True}
        if initial_league:
            initial["league"] = initial_league
        form = GameForm(initial=initial)
        formset = _formset_for_game(league=initial_league)

    roster_names = _roster_names(initial_league or _league_from_form(form))
    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "leader_suggestions": LEADER_SUGGESTIONS,
            "alliance_fields": GameResult.ALLIANCE_FIELDS,
            "roster_names": roster_names,
            "is_edit": False,
        },
    )


def _league_from_form(form):
    if not form.is_bound:
        return form.initial.get("league")
    league = form.data.get("league") or form.initial.get("league")
    if league:
        try:
            return League.objects.get(pk=league)
        except (League.DoesNotExist, ValueError, TypeError):
            return None
    return None


@require_http_methods(["GET", "POST"])
def game_edit(request, pk):
    game = get_object_or_404(Game, pk=pk)
    if request.method == "POST":
        form = GameForm(request.POST, instance=game)
        formset = _formset_for_game(game=game, data=request.POST)
        if form.is_valid() and formset.is_valid():
            game = form.save()
            formset.league = game.league
            for f in formset.forms:
                f.league = game.league
            _save_results(formset)
            return redirect("games:detail", pk=game.pk)
    else:
        form = GameForm(instance=game)
        formset = _formset_for_game(game=game)

    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "leader_suggestions": LEADER_SUGGESTIONS,
            "alliance_fields": GameResult.ALLIANCE_FIELDS,
            "roster_names": _roster_names(game.league),
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

    results = GameResult.objects.filter(game__in=games_qs).select_related(
        "player", "game"
    )
    player_wins = Counter()
    player_games = Counter()
    for r in results:
        player_games[r.player_id] += 1
        if r.is_winner:
            player_wins[r.player_id] += 1

    standings = []
    for player_id, games_played in player_games.most_common():
        player_results = results.filter(player_id=player_id)
        name = player_results.first().player.name
        wins = player_wins[player_id]
        avg_vp = player_results.aggregate(avg=Avg("victory_points"))["avg"]
        avg_sard = player_results.aggregate(avg=Avg("sardaukar_count"))["avg"]
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
    count_games = None
    if current_league:
        league_standings_rows = league_standings(current_league)
        count_games = resolve_scoring_config(current_league)["count_games"]

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
            "count_games": count_games,
        },
    )


def league_list(request):
    leagues = League.objects.annotate(game_count=Count("games"))
    return render(request, "games/league_list.html", {"leagues": leagues})


def league_detail(request, slug):
    league = get_object_or_404(League, slug=slug)
    games = league.games.prefetch_related("results__player")
    scoring_config = resolve_scoring_config(league)
    standings = league_standings(league)
    roster = league.players.order_by("name")
    add_player_form = LeagueAddPlayerForm()
    return render(
        request,
        "games/league_detail.html",
        {
            "league": league,
            "games": games,
            "standings": standings,
            "roster": roster,
            "add_player_form": add_player_form,
            "count_games": scoring_config["count_games"],
        },
    )


@require_http_methods(["POST"])
def league_add_player(request, slug):
    league = get_object_or_404(League, slug=slug)
    form = LeagueAddPlayerForm(request.POST)
    if form.is_valid():
        player = form.save(league)
        messages.success(
            request,
            f"«{player.name}» añadido al plantel de {league.name}.",
        )
    else:
        for err in form.errors.values():
            messages.error(request, err[0])
    return redirect("games:league_detail", slug=slug)


@require_http_methods(["GET", "POST"])
def league_create(request):
    if request.method == "POST":
        form = LeagueForm(request.POST)
        if form.is_valid():
            league = form.save()
            return redirect("games:league_detail", slug=league.slug)
    else:
        form = LeagueForm(
            initial={"scoring_notes": DEFAULT_SCORING_NOTES.strip()}
        )
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
