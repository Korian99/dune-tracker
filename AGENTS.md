# AGENTS.md — Dune Tracker

Guide for AI agents and developers working on this repository.

## Language policy

| Audience | Language | Where |
|----------|----------|--------|
| **End users** (UI) | **Spanish** | Templates (`templates/`), form labels/help/errors (`games/forms.py`), model `TextChoices` display labels, validation messages shown in the browser |
| **Developers** | **English** | This file, `README.md`, code comments, docstrings, commit messages, variable/function names, `games/services/`, Django admin (optional English) |

Do not mix languages on the same surface. When adding features:

- New buttons, headings, empty states, confirms → Spanish
- New models/services documentation → English here and in docstrings

Product names stay as published: *Dune: Imperium*, *Uprising*, *Bloodlines*, faction names (*Emperador*, *Spacing Guild*, etc.).

`LANGUAGE_CODE` is `es` in `config/settings.py`. Prefer explicit Spanish copy in templates over gettext unless the project moves to full i18n files.

## Project summary

Django web app to log **Dune: Imperium — Uprising** (+ **Bloodlines**) board game sessions: players, leaders, VP, alliances, Sardaukar counts, rounds, duration, and **leagues** with standard placement + bonus scoring (`games/services/scoring.py`).

Stack: Django 5, SQLite (local) / PostgreSQL (Render), WhiteNoise, Gunicorn.

## Layout

```
config/              # settings, root URLs
games/               # main Django app
  models.py, views.py, forms.py, urls.py, admin.py
  services/          # domain logic (scoring, tiebreak, hitos, stats, leaders)
  integrations/      # external IO (sheet_io, worker_sync, bgc/)
  admin_helpers/     # admin auth + mixins (not games/admin.py)
  data/              # bundled import payloads (liga_n1, bgc_uprising, …)
  tests/             # test_*.py
  management/commands/
templates/games/     # Spanish UI
static/              # css/, js/, img/, vendor/
AGENTS.md            # this file (English)
README.md            # developer setup (English)
```

Import domain code from `games.services.*` and IO from `games.integrations.*` (migrations use these paths too).

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

### `LeagueHito` (UI: **Hitos**)

- Per-league tracks (`games/hitos.py`), three built-ins on league create:
  - **Highscore** — auto max VP in one game.
  - **Lowscore** — auto min VP in one game.
  - **Powerscore** — manual (`manual_value`, `manual_players` M2M for ties; `manual_player` legacy sync); edit on **Editar liga**.
- `metric`: `auto_max_vp` | `auto_min_vp` | `manual`.

### `Game`

- Optional `league` FK.
- `played_on`, `base_game` (uprising/imperium), `bloodlines`, `player_count`, `rounds`, `duration_minutes`, `notes`.

### `GameResult` (inline per game)

- `player` FK (required), `leader`, `victory_points`
- `sardaukar_count` — Bloodlines Sardaukar commanders (0–14)
- Alliance booleans per result row: `alliance_emperor`, `alliance_guild`, `alliance_bene_gesserit`, `alliance_fremen`. `GameAllianceForm` assigns one holder per faction; the same player may hold any number of factions (including all four).
- `ALLIANCE_FIELDS` — list of `(field_name, Spanish label)` for forms and display
- Unique per game: `(game, player)`

**Game logging UX:** `GameForm` forces Uprising + Bloodlines. Each result row: `player_pick` and `leader` are `<select>` fields enhanced with **Select2** on `game_form.html` (class `enhanced-select`, init in `static/js/enhanced-selects.js`). Alliance holders use the same widget. Players must be chosen from the roster (league plantel or global `Player` list); manage the plantel on **Editar liga**.

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
| `/leagues/<slug>/` | `league_detail` | League standings, hitos, games |
| `/leagues/<slug>/edit/` | `league_edit` | Edit league, roster, powerscore |
| `/leagues/<slug>/players/add/` | `league_add_player` | POST add player (redirects to edit) |
| `/leagues/<slug>/players/<id>/remove/` | `league_remove_player` | POST remove from roster |
| `/leagues/<slug>/export/` | `league_sheet_export` | Download games as pipe-delimited text (Google Sheets format) |

## League scoring

Implemented in `games/services/scoring.py`:

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

Edit per league: **Editar liga** form → “Parámetros de puntuación” (writes `scoring_config` JSON). VP bonus thresholds are a comma-separated list (not fixed to 10/12/15).

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

Migration `0011` reads `ADMIN_USER` / `ADMIN_PASS` from the environment after loading `.env` when present; skips if unset. Creates superuser with empty email; idempotent password/flag updates if the user already exists.

**Delete guards** (`games/delete_guards.py`): leagues with games, players with any game results, and roster removals when the player has results in that league cannot be deleted in Django admin or via **Editar liga** plantel remove (Spanish error messages).

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

League page **Exportar partidas** hits the same format as download. Source data: `games/data/liga_n1.py`; logic: `games/integrations/sheet_io.py`.

### Board Games Companion (BGC) Hive backup

Historical Uprising sessions from the **Board Games Companion** Android app (Flutter Hive `.hive` boxes).

```bash
# Re-export from a new backup zip or extracted folder
python manage.py export_bgc_games "BGC Backup 2026-06-06 141651.zip"

# Import bundled data into Liga N°0 (idempotent by import_key bgc-<playthrough-uuid>)
# Migration `0012` creates `liga-n0` and imports on `migrate` for new databases.
python manage.py import_bgc_games --league liga-n0
python manage.py import_bgc_games --source path/to/backup.zip --league liga-n0 --dry-run
```

- Parser: `games/bgc_hive.py` (BGC model adapters from [BoardGamesCompanion](https://github.com/Progrunning/BoardGamesCompanion))
- Translation: `games/integrations/bgc/io.py` → `games/data/bgc_uprising.py` (BGG `397598` only)
- BGC stores **VP + placement** only; leaders, alliances, Sardaukar, and rounds are not imported.

## Android (Kotlin) companion

Offline mobile rebuild lives in sibling folder `../dune-tracker-android/` (separate git repo recommended). See `docs/MOBILE_KOTLIN.md` and `dune-tracker-android/docs/LEARNING_PATH.md`.

### `CHANGES_PENDING.md` (Android)

When working on the Android app or when web changes affect mobile parity, maintain **`../dune-tracker-android/CHANGES_PENDING.md`**:

- **Create** the file from the template in that repo if it is missing.
- **Append** open bugs, build errors, and web/Android mismatches under **Open** when they cannot be fixed in the same session.
- **Check off / move to Done** when resolved.
- Reference Django paths (e.g. `games/tiebreak.py`, templates) for parity issues.

Agents should read `CHANGES_PENDING.md` at the start of Android-related tasks and update it before finishing if anything remains broken or untested.

Optional: keep a similar `CHANGES_PENDING.md` in this repo for web-only follow-ups.

## Deployment

- **GitHub** — source of truth: `https://github.com/Korian99/dune-tracker`
- **Live app** — Render web + **Neon** Postgres (`DATABASE_URL`), not Render free DB
- **Guide** — `docs/NEON_SETUP.md` (primary), `docs/HOSTING.md` (overview)
- **CI** — `.github/workflows/ci.yml` on push/PR to `main`
