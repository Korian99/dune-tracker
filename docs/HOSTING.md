# Hosting guide (GitHub + live site)

## What GitHub does (and does not)

| Goal | Use |
|------|-----|
| Store code, history, backups | **GitHub** — [github.com/Korian99/dune-tracker](https://github.com/Korian99/dune-tracker) |
| Run the Django app on the internet | **Render** (or similar), connected to that repo |
| Static website only | GitHub Pages — **not suitable** for this project |

GitHub hosts your **repository**. The **web app** runs on a Python host that pulls from GitHub.

## Step 1 — Push code to GitHub

From the project folder:

```powershell
cd d:\Projects\dune-tracker
git add .
git status
git commit -m "Add Dune Tracker Django app"
git push origin main
```

If Git asks you to sign in, use a [Personal Access Token](https://github.com/settings/tokens) as the password (not your GitHub account password), or sign in with GitHub Desktop.

After push, refresh your repo on GitHub — you should see `manage.py`, `games/`, `templates/`, etc.

## Step 2 — Deploy the live app (Render, free tier)

1. Go to [render.com](https://render.com) and sign up (use **Sign in with GitHub**).
2. **New +** → **Blueprint**.
3. Connect repository **Korian99/dune-tracker**.
4. Render reads `render.yaml` and creates:
   - Web service (`dune-tracker`)
   - PostgreSQL database (`dune-tracker-db`)
5. Click **Apply**. Wait for the first deploy (several minutes).
6. Open the web service → **Environment** and set:

   | Variable | Example value |
   |----------|----------------|
   | `ALLOWED_HOSTS` | `dune-tracker.onrender.com` |
   | `CSRF_TRUSTED_ORIGINS` | `https://dune-tracker.onrender.com` |

   Use your real hostname from the Render dashboard (shown at the top of the service).

7. **Manual Deploy** → **Deploy latest commit** if needed after changing env vars.

Your public URL: `https://dune-tracker.onrender.com` (or the name Render assigns).

`build.sh` runs on each deploy: install deps, `collectstatic`, `migrate`.

### Optional: Django admin on production

In Render → **Shell** (or one-off job):

```bash
python manage.py createsuperuser
```

Then visit `https://YOUR-APP.onrender.com/admin/`.

## Step 3 — Updates later

```powershell
git add .
git commit -m "Describe your change"
git push origin main
```

If auto-deploy is enabled on Render, the site rebuilds automatically.

## CI on GitHub

The workflow `.github/workflows/ci.yml` runs `manage.py check` and migrations on every push to `main`. See the **Actions** tab on GitHub.

## Troubleshooting

- **502 / DisallowedHost** — `ALLOWED_HOSTS` must match your Render hostname exactly (no `https://`).
- **CSRF error on login/forms** — set `CSRF_TRUSTED_ORIGINS` to `https://your-host.onrender.com`.
- **Build fails on `build.sh`** — file must use LF line endings (see `.gitattributes`).
- **Free tier sleeps** — first request after idle can take ~30s on Render free plan.

## Database persistence (why Render free hurts)

| Piece | Render free |
|-------|-------------|
| Web service | Works; sleeps when idle |
| Render Postgres | **Expires ~90 days** on free — not a long-term store |
| SQLite on disk | **Lost on redeploy** — disk is ephemeral |

For a personal game log you want **data that stays**. Common patterns:

### Option A — Split stack (best free combo) ⭐

**App** on Render / Fly / Koyeb (free or cheap) + **Postgres elsewhere** (persistent free tier).

| Database host | Free storage | Notes |
|---------------|--------------|--------|
| [Neon](https://neon.tech) | ~0.5 GB | Data persists; DB may **sleep** → 1–3s cold start |
| [Supabase](https://supabase.com) | ~500 MB | Real Postgres; project can pause when idle, **data kept** |
| [DBHost](https://dbhost.app) | 250 MB | Free tier, backups advertised |
| [ElephantSQL](https://www.elephantsql.com) | 20 MB | Tiny but enough for this app |

Set only `DATABASE_URL` on your app host (remove Render’s Postgres). This repo already supports that via `config/settings.py`.

**Good for:** GitHub deploy, $0, real Postgres, hobby scale.

### Option B — One cheap VPS (best long-term sanity)

[Hetzner](https://www.hetzner.com/cloud) (~€4/mo), [Oracle Always Free](https://www.oracle.com/cloud/free/) (ARM VM, $0), or similar: Docker Compose with Django + Postgres (or SQLite on a real disk).

**Good for:** Permanent disk, no cold starts, no 90-day DB expiry, full control.  
**Cost:** €0 (Oracle, more setup) or ~€4/mo.

### Option C — SQLite on a persistent volume

For **only you and friends**, a few hundred games fit easily in SQLite. Mount persistent storage:

- **Fly.io** — attach a [volume](https://fly.io/docs/reference/volumes/) and point `DATABASE_URL` / `NAME` at `/data/db.sqlite3`
- **VPS** — file on disk as today locally

**Good for:** Simplest ops, no separate DB service.  
**Bad for:** Heavy traffic or many concurrent writers (not your case).

### Option D — PaaS with included DB (paid or trial)

| Service | Persistence |
|---------|-------------|
| [PythonAnywhere](https://www.pythonanywhere.com) | Free tier uses **MySQL** (would need Django DB change); paid plans persistent |
| [Railway](https://railway.app) | ~$5/mo credit; DB + app together, data persists while you pay |
| Render **paid** Postgres | From ~$7/mo — stays with Render |

### What we recommend for Dune Tracker

1. **$0:** Render (web only) + **Neon** or **Supabase** `DATABASE_URL` — see [Deploy with external Postgres](#deploy-with-external-postgres-neon--render) below.  
2. **Low cost, no surprises:** Hetzner + Docker Compose.  
3. **Minimal moving parts:** Fly.io + volume + SQLite.

GitHub stays the **code** host in all cases; none of these replace GitHub.

---

## Deploy with external Postgres (Neon + Render)

1. Create a project at [neon.tech](https://neon.tech) → copy the **connection string** (`postgresql://...`).
2. On Render: **New → Web Service** (not Blueprint with Render DB), connect `Korian99/dune-tracker`.
   - Build: `chmod +x build.sh && ./build.sh`
   - Start: `gunicorn config.wsgi:application`
3. Environment variables:

   | Variable | Value |
   |----------|--------|
   | `DATABASE_URL` | Neon connection string |
   | `SECRET_KEY` | long random string |
   | `DEBUG` | `false` |
   | `ALLOWED_HOSTS` | `your-app.onrender.com` |
   | `CSRF_TRUSTED_ORIGINS` | `https://your-app.onrender.com` |

4. Do **not** attach Render Postgres on free tier if you want long-term data.

Optional: remove the `databases:` block from `render.yaml` in this repo so Blueprint does not create a 90-day DB.

---

## Self-host at home (free, SQLite, Cloudflare Tunnel)

To avoid Render/Neon bills and run on your **home PC** with a public HTTPS link, see **[CLOUDFLARE_HOME.md](CLOUDFLARE_HOME.md)** (mateousa Cloudflare account, no corporate proxy).

---

## Alternatives to Render (app host)

Any host that runs Python from GitHub works: Fly.io, Koyeb, Railway, PythonAnywhere, a VPS. Use `build.sh` + `gunicorn config.wsgi:application` and set `DATABASE_URL`.
