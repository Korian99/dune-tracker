from datetime import date

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import (
    GameAllianceForm,
    GameForm,
    GameResultFormSet,
    LeagueAddPlayerForm,
    LeagueForm,
    _player_choice_list,
)
from .models import Game, GameResult, League
from .sheet_io import export_league_sheet
from .scoring import (
    DEFAULT_SCORING_NOTES,
    breakdown_display,
    compute_league_points_breakdown,
    league_standings,
    resolve_scoring_config,
)


def _save_results(formset, alliance_data=None):
    """Save result rows; always apply alliances against full game results."""
    results = formset.save()
    game = formset.instance
    for i, result in enumerate(results):
        if result.order != i:
            result.order = i
            result.save(update_fields=["order"])
    if game and game.pk:
        db_results = list(
            GameResult.objects.filter(game=game).select_related("player")
        )
        if alliance_data is not None:
            _apply_alliances(db_results, alliance_data)
        return db_results if alliance_data is not None else (results or db_results)
    return results


def _apply_alliances(results, alliance_data):
    fields = [f for f, _ in GameResult.ALLIANCE_FIELDS]
    for result in results:
        for field in fields:
            setattr(result, field, False)
    by_name = {r.player.name: r for r in results}
    for field, _label in GameResult.ALLIANCE_FIELDS:
        holder = (alliance_data.get(field) or "").strip()
        if holder and holder in by_name:
            setattr(by_name[holder], field, True)
    for result in results:
        result.save(update_fields=fields)


def _alliance_initial_from_game(game):
    initial = {}
    for result in game.results.select_related("player"):
        for field, _label in GameResult.ALLIANCE_FIELDS:
            if getattr(result, field):
                initial[field] = result.player.name
    return initial


def _alliance_player_names(request, game=None, league=None):
    """Names valid for alliance dropdowns (players in this game + POST rows)."""
    names = set()
    if game:
        names.update(
            game.results.select_related("player").values_list("player__name", flat=True)
        )
    if request.method == "POST":
        total = int(request.POST.get("results-TOTAL_FORMS", 0))
        for i in range(total):
            val = request.POST.get(f"results-{i}-player_pick", "").strip()
            if val:
                names.add(val)
        for field, _ in GameResult.ALLIANCE_FIELDS:
            val = request.POST.get(field, "").strip()
            if val:
                names.add(val)
    if not names:
        names.update(_player_choice_list(league))
    return sorted(names)


def _alliance_form_for_request(request, formset, game=None, league=None):
    """Build alliance form; on POST use submitted player rows for choices."""
    league = league or (game.league if game and game.league_id else None)
    names = _alliance_player_names(request, game=game, league=league)
    if request.method == "POST":
        return GameAllianceForm(request.POST, player_names=names)
    initial = _alliance_initial_from_game(game) if game else None
    return GameAllianceForm(player_names=names, initial_assignments=initial)


def _games_queryset(league_slug=None):
    qs = Game.objects.select_related("league").prefetch_related(
        "results__player"
    )
    if league_slug:
        qs = qs.filter(league__slug=league_slug)
    return qs


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
        league_for_formset = _league_from_form(form) or initial_league
        if form.is_valid():
            league_for_formset = form.cleaned_data.get("league") or league_for_formset
        formset = _formset_for_game(league=league_for_formset, data=request.POST)
        alliance_form = _alliance_form_for_request(
            request, formset, league=league_for_formset
        )
        if form.is_valid() and formset.is_valid() and alliance_form.is_valid():
            game = form.save()
            formset.instance = game
            formset.league = game.league
            for f in formset.forms:
                f.league = game.league
            _save_results(formset, alliance_form.cleaned_data)
            return redirect("games:detail", pk=game.pk)
    else:
        initial = {
            "played_on": date.today(),
            "player_count": Game.PlayerCount.FOUR,
        }
        if initial_league:
            initial["league"] = initial_league
        form = GameForm(initial=initial)
        formset = _formset_for_game(league=initial_league)
        alliance_form = _alliance_form_for_request(
            request, formset, league=initial_league
        )

    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "alliance_form": alliance_form,
            "is_edit": False,
        },
    )


def _league_from_form(form):
    if not form.is_bound:
        league = form.initial.get("league")
        if league:
            return league
        return None
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
        league_for_formset = _league_from_form(form) or game.league
        if form.is_valid():
            league_for_formset = form.cleaned_data.get("league") or league_for_formset
        formset = _formset_for_game(game=game, data=request.POST)
        formset.league = league_for_formset
        for f in formset.forms:
            f.league = league_for_formset
        alliance_form = _alliance_form_for_request(
            request, formset, game=game, league=league_for_formset
        )
        if form.is_valid() and formset.is_valid() and alliance_form.is_valid():
            game = form.save()
            formset.league = game.league
            for f in formset.forms:
                f.league = game.league
            _save_results(formset, alliance_form.cleaned_data)
            return redirect("games:detail", pk=game.pk)
    else:
        form = GameForm(instance=game)
        formset = _formset_for_game(game=game)
        formset.league = game.league
        for f in formset.forms:
            f.league = game.league
        alliance_form = _alliance_form_for_request(
            request, formset, game=game, league=game.league
        )

    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "alliance_form": alliance_form,
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
    from .stats_queries import parse_stats_filter, stats_for_filter

    league_slugs, include_casual = parse_stats_filter(request)
    # Legacy single-league links: ?league=slug
    legacy_slug = request.GET.get("league")
    if legacy_slug and legacy_slug not in league_slugs:
        league_slugs = [legacy_slug]
        include_casual = False

    data = stats_for_filter(league_slugs, include_casual)
    all_leagues = League.objects.order_by("name")

    return render(
        request,
        "games/stats.html",
        {
            "all_leagues": all_leagues,
            "selected_league_slugs": set(data["league_slugs"]),
            "include_casual": data["include_casual"],
            "scope_label": data["scope_label"],
            "summary": data["summary"],
            "player_rows": data["player_rows"],
            "leader_rows": data["leader_rows"],
            "league_standings": data["league_standings"],
            "count_games": data["count_games"],
            "use_league_scoring": data["use_league_scoring"],
            "single_league": data["single_league"],
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


@require_http_methods(["GET"])
def league_sheet_export(request, slug):
    """Download league games in Google Sheets pipe format."""
    league = get_object_or_404(League, slug=slug)
    text = export_league_sheet(league)
    filename = f"{league.slug}-partidas.txt"
    response = HttpResponse(text, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_http_methods(["POST"])
def league_add_player(request, slug):
    league = get_object_or_404(League, slug=slug)
    form = LeagueAddPlayerForm(request.POST)
    if form.is_valid():
        player = form.save(league)
        messages.success(request, f"«{player.name}» añadido al plantel.")
    else:
        for err in form.errors.get("name", []):
            messages.error(request, err)
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
