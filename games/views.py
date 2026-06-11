from datetime import date

from django.contrib import messages
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import (
    GameAllianceForm,
    GameForm,
    GameResultFormSet,
    LeagueAddPlayerForm,
    LeagueForm,
    _player_choice_list,
)
from .models import Game, GameResult, League, LeagueMembership

LEAGUE_GAMES_PER_PAGE = 20
from games.integrations.sheet_io import export_league_sheet
from games.services.tiebreak import (
    apply_tiebreaks_from_post,
    game_needs_tiebreak,
    has_top_vp_tie,
    has_vp_ties,
    normalize_tiebreaks_after_save,
    selected_tiebreak_for_group,
    vp_tie_groups,
)
from games.services.scoring import (
    DEFAULT_SCORING_NOTES,
    league_score_rows_for_game,
    league_standings,
    resolve_scoring_config,
)


def _save_results(formset, alliance_data=None):
    """Save result rows; always apply alliances against full game results."""
    results = formset.save()
    game = formset.instance
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


def _return_sort_from_request(request) -> str:
    """Games list sort on league detail after save (newest or oldest)."""
    raw = (request.POST.get("return_sort") or request.GET.get("return_sort") or "newest").strip().lower()
    return "oldest" if raw == "oldest" else "newest"


def _league_games_queryset(league: League, games_sort: str):
    games = league.games.select_related("designated_winner__player").prefetch_related(
        "results__player"
    )
    if games_sort == "oldest":
        return games.order_by("played_on", "created_at")
    return games.order_by("-played_on", "-created_at")


def _league_game_page_number(game: Game, games_sort: str) -> int:
    """1-based page for a game in the paginated league games list."""
    if not game.league_id:
        return 1
    game_pks = list(_league_games_queryset(game.league, games_sort).values_list("pk", flat=True))
    try:
        index = game_pks.index(game.pk)
    except ValueError:
        return 1
    return index // LEAGUE_GAMES_PER_PAGE + 1


def _league_game_url(game, *, return_sort: str = "newest") -> str | None:
    """League detail URL scrolled to a game card, or None if not a league game."""
    if not game.league_id:
        return None
    sort = "oldest" if return_sort == "oldest" else "newest"
    base = reverse("games:league_detail", kwargs={"slug": game.league.slug})
    page = _league_game_page_number(game, sort)
    query = f"sort={sort}"
    if page > 1:
        query += f"&page={page}"
    return f"{base}?{query}#game-{game.pk}"


def _redirect_after_game_save(game, request):
    """Revisit tiebreak when any VP level is tied; else league detail or game detail."""
    game.refresh_from_db()
    normalize_tiebreaks_after_save(game)
    return_sort = _return_sort_from_request(request)
    if has_vp_ties(game):
        url = reverse("games:resolve_tie", kwargs={"pk": game.pk})
        if game.league_id:
            url += f"?return_sort={return_sort}"
        return redirect(url)
    league_url = _league_game_url(game, return_sort=return_sort)
    if league_url:
        return redirect(league_url)
    return redirect("games:detail", pk=game.pk)


def _games_queryset(league_slug=None):
    qs = Game.objects.select_related(
        "league", "designated_winner__player"
    ).prefetch_related("results__player")
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
        Game.objects.select_related(
            "league", "designated_winner__player"
        ).prefetch_related("results__player"),
        pk=pk,
    )
    alliance_map = _alliance_map_for_game(game)
    league_score_rows = None
    if game.league_id:
        league_score_rows = league_score_rows_for_game(game, game.league)
    return_sort = _return_sort_from_request(request)
    league_back_url = (
        _league_game_url(game, return_sort=return_sort) if game.league_id else None
    )
    return render(
        request,
        "games/game_detail.html",
        {
            "game": game,
            "alliance_map": alliance_map,
            "league_score_rows": league_score_rows,
            "needs_tiebreak": game_needs_tiebreak(game),
            "has_vp_ties": has_vp_ties(game),
            "has_top_vp_tie": has_top_vp_tie(game),
            "tie_groups": vp_tie_groups(game),
            "return_sort": return_sort,
            "league_back_url": league_back_url,
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
            return _redirect_after_game_save(game, request)
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
            "return_sort": _return_sort_from_request(request),
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
            return _redirect_after_game_save(game, request)
    else:
        form = GameForm(instance=game)
        formset = _formset_for_game(game=game)
        formset.league = game.league
        for f in formset.forms:
            f.league = game.league
        alliance_form = _alliance_form_for_request(
            request, formset, game=game, league=game.league
        )

    return_sort = _return_sort_from_request(request) if game.league_id else "newest"
    return render(
        request,
        "games/game_form.html",
        {
            "form": form,
            "formset": formset,
            "alliance_form": alliance_form,
            "is_edit": True,
            "game": game,
            "return_sort": return_sort,
        },
    )


@require_http_methods(["GET", "POST"])
def game_resolve_tie(request, pk):
    game = get_object_or_404(
        Game.objects.select_related("league", "designated_winner__player").prefetch_related(
            "results__player"
        ),
        pk=pk,
    )
    groups = vp_tie_groups(game)
    return_sort = _return_sort_from_request(request)
    if not groups:
        league_url = _league_game_url(game, return_sort=return_sort)
        if league_url:
            return redirect(league_url)
        return redirect("games:detail", pk=game.pk)

    if request.method == "POST":
        form_errors = None
        try:
            apply_tiebreaks_from_post(game, request.POST)
        except ValueError as exc:
            form_errors = str(exc)
        else:
            messages.success(request, "Desempate guardado.")
            league_url = _league_game_url(game, return_sort=return_sort)
            if league_url:
                return redirect(league_url)
            return redirect("games:detail", pk=game.pk)

        return _render_tiebreak_page(
            request, game, groups, form_errors=form_errors, return_sort=return_sort
        )

    return _render_tiebreak_page(request, game, groups, return_sort=return_sort)


def _render_tiebreak_page(request, game, groups, form_errors=None, return_sort="newest"):
    tie_groups = []
    for group in groups:
        state = selected_tiebreak_for_group(game, group)
        ranks = state.get("ranks") or {}
        result_rows = [
            {
                "result": result,
                "selected_rank": ranks.get(result.pk, ""),
            }
            for result in group["results"]
        ]
        tie_groups.append({**group, **state, "result_rows": result_rows})
    skip_url = _league_game_url(game, return_sort=return_sort) or reverse(
        "games:detail", kwargs={"pk": game.pk}
    )
    return render(
        request,
        "games/game_tiebreak.html",
        {
            "game": game,
            "tie_groups": tie_groups,
            "needs_resolution": game_needs_tiebreak(game),
            "can_skip": not game_needs_tiebreak(game),
            "form_errors": form_errors,
            "return_sort": return_sort,
            "skip_url": skip_url,
        },
    )


@require_http_methods(["POST"])
def game_delete(request, pk):
    game = get_object_or_404(Game, pk=pk)
    game.delete()
    return redirect("games:list")


def stats(request):
    from games.services.stats_queries import parse_stats_filter, stats_for_filter

    league_slugs, include_casual, player_slugs = parse_stats_filter(request)
    # Legacy single-league links: ?league=slug
    legacy_slug = request.GET.get("league")
    if legacy_slug and legacy_slug not in league_slugs:
        league_slugs = [legacy_slug]
        include_casual = False

    data = stats_for_filter(
        league_slugs, include_casual, player_slugs=player_slugs
    )
    all_leagues = League.objects.order_by("name")

    return render(
        request,
        "games/stats.html",
        {
            "all_leagues": all_leagues,
            "selected_league_slugs": set(data["league_slugs"]),
            "selected_player_slugs": set(data["player_slugs"]),
            "filter_players": data["filter_players"],
            "leader_filter_label": data["leader_filter_label"],
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
    leagues = League.objects.all()
    return render(request, "games/league_list.html", {"leagues": leagues})


def _league_games_sort(request) -> str:
    """Return 'oldest' or 'newest' from query string (default newest)."""
    sort = (request.GET.get("sort") or "newest").strip().lower()
    return "oldest" if sort == "oldest" else "newest"


def _league_fecha_numbers(league: League) -> dict[int, int]:
    """Map game pk → Fecha N° (1 = oldest by played_on, then created_at)."""
    ordered_pks = league.games.order_by("played_on", "created_at").values_list(
        "pk", flat=True
    )
    return {pk: index + 1 for index, pk in enumerate(ordered_pks)}


def league_detail(request, slug):
    from games.services.hitos import league_hito_snapshots

    league = get_object_or_404(League, slug=slug)
    games_sort = _league_games_sort(request)
    fecha_by_pk = _league_fecha_numbers(league)
    games_qs = _league_games_queryset(league, games_sort)
    paginator = Paginator(games_qs, LEAGUE_GAMES_PER_PAGE)
    page_num = request.GET.get("page", "1")
    try:
        games_page = paginator.page(page_num)
    except PageNotAnInteger:
        games_page = paginator.page(1)
    except EmptyPage:
        games_page = paginator.page(paginator.num_pages)
    scoring_config = resolve_scoring_config(league)
    standings = league_standings(league)
    game_entries = [
        {
            "game": game,
            "fecha_number": fecha_by_pk[game.pk],
            "league_score_rows": league_score_rows_for_game(game, league),
        }
        for game in games_page.object_list
    ]
    return render(
        request,
        "games/league_detail.html",
        {
            "league": league,
            "game_entries": game_entries,
            "games_page": games_page,
            "standings": standings,
            "hito_snapshots": league_hito_snapshots(league),
            "count_games": scoring_config["count_games"],
            "games_sort": games_sort,
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
    return redirect("games:league_edit", slug=slug)


@require_http_methods(["POST"])
def league_remove_player(request, slug, player_id):
    from django.core.exceptions import ValidationError
    from games.services.delete_guards import ensure_league_roster_can_remove

    league = get_object_or_404(League, slug=slug)
    membership = get_object_or_404(
        LeagueMembership, league=league, player_id=player_id
    )
    name = membership.player.name
    try:
        ensure_league_roster_can_remove(league, membership.player)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect("games:league_edit", slug=slug)
    membership.delete()
    messages.success(request, f"«{name}» quitado del plantel.")
    return redirect("games:league_edit", slug=slug)


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
    roster = league.players.order_by("name")
    return render(
        request,
        "games/league_form.html",
        {
            "form": form,
            "is_edit": True,
            "league": league,
            "roster": roster,
            "add_player_form": LeagueAddPlayerForm(),
        },
    )
