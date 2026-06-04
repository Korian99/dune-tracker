# Dune Tracker

A small Django web app to log your **Dune: Imperium — Uprising** games (with optional **Bloodlines** expansion): dates, leaders, victory points, alliances, Sardaukar, rounds, duration, leagues, and standings.

**UI language:** Spanish (user-facing). **Developer docs:** English — see [AGENTS.md](AGENTS.md).

> **Note:** GitHub stores your code; it does not run Django. Push to GitHub, then deploy with **Render** (free) using `render.yaml`. Full walkthrough: **[docs/HOSTING.md](docs/HOSTING.md)**.

**Repo:** [github.com/Korian99/dune-tracker](https://github.com/Korian99/dune-tracker)

## Features

- Log games: date, edition, Bloodlines, league, rounds, duration, notes
- Per player: name, leader, VP, Sardaukar count, faction alliances (one per faction)
- Leagues with documented scoring rules (automated points: placeholder in `games/scoring.py`)
- Stats and league standings (Spanish UI)
- Django admin at `/admin/` for power users

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env          # edit SECRET_KEY if you like
python manage.py migrate
python manage.py runserver
```

Open [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

Optional: Django admin — set `ADMIN_USER` and `ADMIN_PASS` in `.env` (or Render env vars), then run `migrate`. Migration `0011` creates or updates that superuser. Log in at `/admin/` with **username + password** (`ADMIN_USER`, not email). `createsuperuser` also skips the email prompt.

## Host on GitHub + go live

```powershell
git add .
git commit -m "Your message"
git push origin main
```

Then deploy from GitHub on [Render](https://render.com) + **[Neon](https://neon.tech)** for the database. Step-by-step: **[docs/NEON_SETUP.md](docs/NEON_SETUP.md)**. Overview: **[docs/HOSTING.md](docs/HOSTING.md)**.

## Project layout

| Path | Purpose |
|------|---------|
| `games/` | Models, views, forms |
| `config/` | Django settings & URLs |
| `templates/` | HTML templates |
| `static/` | CSS |
| `render.yaml` | One-click Render deploy |
| `build.sh` | Install deps, collectstatic, migrate |

## Tech stack

- Django 5
- SQLite (local) or PostgreSQL (Render)
- WhiteNoise for static files
- Gunicorn in production
