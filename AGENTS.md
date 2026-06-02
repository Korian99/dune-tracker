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

Django web app to log **Dune: Imperium — Uprising** (+ **Bloodlines**) board game sessions: players, leaders, VP, alliances, Sardaukar counts, rounds, duration, and **leagues** with custom scoring (rules TBD).

Stack: Django 5, SQLite (local) / PostgreSQL (Render), WhiteNoise, Gunicorn.

## Layout

```
config/           # settings, root URLs
games/            # main app
  models.py       # League, Game, GameResult
  forms.py        # GameForm, GameResultFormSet, LeagueForm (Spanish UI strings)
  views.py        # CRUD + stats
  scoring.py      # League points (placeholder until scoring_config defined)
  urls.py
templates/games/  # Spanish UI
static/css/       # style.css
AGENTS.md         # this file (English)
README.md         # developer setup (English)
```

## Data model

### `League`

- Groups games under shared rules.
- `scoring_notes` — human-readable rules (Spanish prose from users).
- `scoring_config` — JSON for automated scoring (implement in `games/scoring.py` when rules are defined).

### `Game`

- Optional `league` FK.
- `played_on`, `base_game` (uprising/imperium), `bloodlines`, `player_count`, `rounds`, `duration_minutes`, `notes`.

### `GameResult` (inline per game)

- `player_name`, `leader`, `victory_points`
- `sardaukar_count` — Bloodlines Sardaukar commanders (0–14)
- Alliance booleans (one player per faction per game): `alliance_emperor`, `alliance_guild`, `alliance_bene_gesserit`, `alliance_fremen`
- `ALLIANCE_FIELDS` — list of `(field_name, Spanish label)` for forms and display

## URLs (`games` namespace)

| Path | Name | Purpose |
|------|------|---------|
| `/` | `home` | Dashboard |
| `/games/` | `list` | All games (`?league=slug`) |
| `/games/new/` | `create` | Log game (`?league=slug`) |
| `/games/<id>/` | `detail` | Game detail |
| `/games/<id>/edit/` | `edit` | Edit |
| `/games/<id>/delete/` | `delete` | POST delete |
| `/stats/` | `stats` | Stats (`?league=slug`) |
| `/leagues/` | `league_list` | Leagues |
| `/leagues/new/` | `league_create` | Create league |
| `/leagues/<slug>/` | `league_detail` | League + standings |
| `/leagues/<slug>/edit/` | `league_edit` | Edit league |

## League scoring (TODO)

Implement custom logic in `games/scoring.py`:

- `compute_league_points(result, league)` — points for one player in one game
- `league_standings(league)` — aggregated table

Current default: placement points `{1: 3, 2: 2, 3: 1}` unless `league.scoring_config["system"] == "victory_points"`.

When the user provides rules, document the `scoring_config` JSON schema here and implement the branch.

## Conventions

- Keep diffs small; match existing patterns.
- User strings: Spanish in `forms.py` / templates, not hardcoded in views.
- Run `python manage.py makemigrations` / `migrate` after model changes.
- Do not commit secrets, `db.sqlite3`, or `.env`.
- Commits only when the user asks.

## Local commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Deployment

- **GitHub** — source of truth: `https://github.com/Korian99/dune-tracker`
- **Live app** — Render (Blueprint + `render.yaml`), not GitHub Pages
- **Guide** — `docs/HOSTING.md` (push to GitHub, connect Render, env vars)
- **CI** — `.github/workflows/ci.yml` on push/PR to `main`
