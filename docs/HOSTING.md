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

## Alternatives to Render

Any host that runs Python + Postgres from GitHub works: Railway, Fly.io, PythonAnywhere, a VPS. This repo is tuned for Render via `render.yaml` and `build.sh`.
