# AGENTS.md — Dune Tracker

Guide for AI agents and developers working on this repository.

## Language policy

| Audience | Language | Where |
|----------|----------|--------|
| **End users** (UI) | **Spanish** | Templates (`templates/`), form labels/help/errors (`games/forms.py`), model `TextChoices` display labels, validation messages shown in the browser |
| **Developers** | **English** | This file, `README.md`, code comments, docstrings, commit messages, variable/function names, `games/scoring.py`, Django admin (optional English) |

Do not mix languages on the same surface. When adding features:

- New buttons, headings, empty states, confirms → Spanish
- New models/services documentation → English here and in docstrings

Product names stay as published: *Dune: Imperium*, *Uprising*, *Bloodlines*, faction names (*Emperador*, *Gremio*, etc.).

`LANGUAGE_CODE` is `es` in `config/settings.py`. Prefer explicit Spanish copy in templates over gettext unless the project moves to full i18n files.

## Project summary

Django web app to log **Dune: Imperium — Uprising** (+ **Bloodlines**) board game sessions: players, leaders, VP, alliances, Sardaukar counts, rounds, duration, and **leagues** with standard placement + bonus scoring (`games/scoring.py`).

Stack: Django 5, SQLite (local) / PostgreSQL (Render), WhiteNoise, Gunicorn.

## Layout

```
config/           # settings, root URLs
games/            # main app
  models.py       # Player, League, LeagueMembership, Game, GameResult
  forms.py        # GameForm, GameResultFormSet, LeagueForm, LeagueAddPlayerForm
  views.py        # CRUD + stats
  scoring.py      # League points (standard + victory_points override)
  urls.py
templates/games/  # Spanish UI
static/css/       # style.css, select2-dune.css
static/js/        # enhanced-selects.js (game form only)
static/vendor/    # jquery, select2 (vendored)
AGENTS.md         # this file (English)
README.md         # developer setup (English)
```

## Data model

### `Player`

- `name` (unique), `slug`, `created_at`
- `resolve_player(name, league=None)` — get/create player; auto-adds `LeagueMembership` when `league` is set

### `League`

- Groups games under shared rules.
- `players` M2M through `LeagueMembership` (`joined_at`) — league roster
- `scoring_notes` — human-readable rules (Spanish prose from users).
- `scoring_config` — JSON (`system`: `standard` or `victory_points`); see League scoring below.

### `LeagueMembership`

- Through table: `league` + `player`, unique together.

### `Game`

- Optional `league` FK.
- `played_on`, `base_game` (uprising/imperium), `bloodlines`, `player_count`, `rounds`, `duration_minutes`, `notes`.

### `GameResult` (inline per game)

- `player` FK (required), `leader`, `victory_points`
- `sardaukar_count` — Bloodlines Sardaukar commanders (0–14)
- Alliance booleans per result row: `alliance_emperor`, `alliance_guild`, `alliance_bene_gesserit`, `alliance_fremen`. `GameAllianceForm` assigns one holder per faction; the same player may hold any number of factions (including all four).
- `ALLIANCE_FIELDS` — list of `(field_name, Spanish label)` for forms and display
- Unique per game: `(game, player)`

**Game logging UX:** `GameForm` forces Uprising + Bloodlines. Each result row: `player_pick` and `leader` are `<select>` fields enhanced with **Select2** on `game_form.html` (class `enhanced-select`, init in `static/js/enhanced-selects.js`). Alliance holders use the same widget. Players must be chosen from the roster (league plantel or global `Player` list); add names via the league page first.

### Migration `0004`

- Creates `Player` / `LeagueMembership`; migrates distinct legacy `player_name` strings to `Player` (global unique names); adds league memberships for players in league games.

## URLs (`games` namespace)

| Path | Name | Purpose |
|------|------|---------|
| `/` | `home` | Dashboard |
| `/games/` | `list` | All games (`?league=slug`) |
| `/games/new/` | `create` | Log game (`?league=slug`) |
| `/games/<id>/` | `detail` | Game detail |
| `/games/<id>/edit/` | `edit` | Edit |
| `/games/<id>/delete/` | `delete` | POST delete |
| `/stats/` | `stats` | Stats explorer (`?leagues=slug&casual=1`; legacy `?league=slug`) |
| `/leagues/` | `league_list` | Leagues |
| `/leagues/new/` | `league_create` | Create league |
| `/leagues/<slug>/` | `league_detail` | League + roster + standings |
| `/leagues/<slug>/edit/` | `league_edit` | Edit league |
| `/leagues/<slug>/players/add/` | `league_add_player` | POST add player to roster |
| `/leagues/<slug>/export/` | `league_sheet_export` | Download games as pipe-delimited text (Google Sheets format) |

## League scoring

Implemented in `games/scoring.py`:

- `compute_league_points(result, league)` — total points for one player in one game
- `compute_league_points_breakdown(result, league)` — components (placement, bonuses)
- `league_standings(league)` — aggregated table sorted by points, wins, avg VP
- `games/stats_queries.py` — `stats_for_filter()`, player/leader aggregates for filtered games

### Standard system (default)

Used when `scoring_config` is empty or `system` is `"standard"`. Canonical defaults in `games/defaults.py` (DB default + migration `0003`). Runtime merge via `resolve_scoring_config(league)`.

| Key | Default | Meaning |
|-----|---------|---------|
| `count_games` | `8` | Only the best N per-game scores count toward standings (`0` = all) |
| `placement_points` | `{1:5, 2:3, 3:2, 4:1}` | Points by `GameResult.placement` |
| `early_win_max_round` | `6` | +1 if max VP and `1 <= game.rounds <= N` (`0` = off) |
| `vp_thresholds` | `[10, 12, 15]` | +1 each time final VP ≥ threshold (stacking) |

**Ties:** Placement = competition ranking by VP. Early-win = all players at max VP (not `is_winner` pk tie-break).

**Best-N:** `league_standings()` sorts each player’s games by points descending and sums only `count_games` (discards worst).

Edit per league: **Editar liga** form → “Parámetros de puntuación” (writes `scoring_config` JSON).

### `scoring_config` JSON example

```json
{
  "system": "standard",
  "count_games": 8,
  "placement_points": { "1": 5, "2": 3, "3": 2, "4": 1 },
  "early_win_max_round": 6,
  "vp_thresholds": [10, 12, 15]
}
```

```json
{ "system": "victory_points", "count_games": 8 }
```

League points per game = `victory_points`; best-N still applies.

## Conventions

- Keep diffs small; match existing patterns.
- User strings: Spanish in `forms.py` / templates, not hardcoded in views.
- Run `python manage.py makemigrations` / `migrate` after model changes.
- Do not commit secrets, `db.sqlite3`, or `.env`.

### Git: commit and push

- **Never** commit or push unless the user explicitly asks in that turn.
- **After finishing work** for a prompt (feature, fix, or doc update), **always ask** whether you should commit and push — e.g. “¿Hago commit y push?” Do not assume yes; wait for confirmation unless they already said to in the same message.
- When the user asks to commit: stage only relevant files, write a clear English commit message (why, not just what), run `git status` after commit, push only if they asked to push (or said “commit and push”).

## Local commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Sheet import/export (Liga N°1 historical data)

Migration `0005` imports 11 May 2026 games into league slug `liga-n1` when that league exists at migrate time. Otherwise run:

```bash
python manage.py import_sheet_games --league liga-n1
```

Export (stdout or file):

```bash
python manage.py export_sheet_games liga-n1
python manage.py export_sheet_games liga-n1 -o partidas.txt
```

League page **Exportar partidas** hits the same format as download. Source data: `games/data/liga_n1_sheet.py`; logic: `games/sheet_io.py`.

## Deployment

- **GitHub** — source of truth: `https://github.com/Korian99/dune-tracker`
- **Live app** — Render web + **Neon** Postgres (`DATABASE_URL`), not Render free DB
- **Guide** — `docs/NEON_SETUP.md` (primary), `docs/HOSTING.md` (overview)
- **CI** — `.github/workflows/ci.yml` on push/PR to `main`
