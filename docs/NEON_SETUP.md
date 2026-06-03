# Neon + Render setup (Dune Tracker)

Persistent database on **Neon** (free). Django app on **Render** (free web). Code on **GitHub**.

---

## Part 1 — Create the database on Neon

1. Open [https://neon.tech](https://neon.tech) and sign up (GitHub login is fine).

2. **Create a project**
   - Name: e.g. `dune-tracker`
   - Region: pick one close to you (e.g. `EU Central`)
   - Postgres version: default (16) is fine

3. **Copy the connection string**
   - In the Neon dashboard: your project → **Connect**
   - Choose **Django** (or “Connection string”)
   - Use the **direct** connection (not pooler) — hostname **without** `-pooler` in the name  
     Example shape:
     ```
     postgresql://USER:PASSWORD@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
     ```
   - Click **Copy** and store it somewhere safe (password is inside the URL).

4. Keep the dashboard open — you’ll paste this into Render in Part 2.

---

## Part 2 — Deploy the app on Render

### If you already deployed with Render Postgres (Blueprint)

1. [dashboard.render.com](https://dashboard.render.com) → your **dune-tracker** web service  
2. **Environment** → delete any old `DATABASE_URL` tied to Render Postgres (optional: delete the Render Postgres instance in **Databases** to avoid confusion).  
3. Continue below with the new Neon `DATABASE_URL`.

### New deploy (recommended)

1. [dashboard.render.com](https://dashboard.render.com) → **New +** → **Blueprint**  
2. Connect repo **Korian99/dune-tracker** (branch `main`).  
3. Render reads `render.yaml` — only a **web service**, no Render database.  
4. Before or right after **Apply**, open the web service → **Environment** and add:

   | Key | Value |
   |-----|--------|
   | `DATABASE_URL` | Paste Neon connection string (full `postgresql://...`) |
   | `ALLOWED_HOSTS` | `dune-tracker.onrender.com` (use **your** Render URL, no `https://`) |
   | `CSRF_TRUSTED_ORIGINS` | `https://dune-tracker.onrender.com` (with `https://`) |

   `SECRET_KEY` and `DEBUG=false` come from `render.yaml`.

5. **Save** → **Manual Deploy** → **Deploy latest commit**.

6. Wait until status is **Live**. Open your URL (e.g. `https://dune-tracker.onrender.com`).

The build runs `migrate` automatically — tables are created on Neon on first deploy.

---

## Part 3 — Check it works

1. Open the site → register a test game.  
2. In Neon: **Tables** / SQL editor → you should see Django tables (`games_game`, etc.).  
3. Redeploy once on Render → data should **still be there** (unlike Render free Postgres after 90 days).

### Optional: Django admin

Render → your service → **Shell**:

```bash
python manage.py createsuperuser
```

Visit `https://YOUR-APP.onrender.com/admin/`.

---

## Part 4 — Use Neon locally (optional)

Test against the same cloud DB from your PC:

```powershell
cd d:\Projects\dune-tracker
.venv\Scripts\activate
$env:DATABASE_URL = "postgresql://USER:PASSWORD@ep-....neon.tech/neondb?sslmode=require"
python manage.py migrate
python manage.py runserver
```

Or put `DATABASE_URL=...` in a local `.env` file (do **not** commit `.env`).

Without `DATABASE_URL`, the app uses local `db.sqlite3` as before.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `SSL connection required` | Neon URL must include `?sslmode=require` (Neon’s copy button usually adds it). |
| `DisallowedHost` | `ALLOWED_HOSTS` = exact Render hostname only. |
| CSRF failed | `CSRF_TRUSTED_ORIGINS` = `https://` + same hostname. |
| Build OK, 500 on first hit | Check **Logs** on Render; often wrong `DATABASE_URL` or password with special characters (URL-encode if needed). |
| Slow first load after hours | Neon + Render free tier **sleep when idle** — first click wakes both (5–30 s). Normal. |
| Error / “not found” until you refresh | Stale DB connection or cold start failed. Fixed with `CONN_MAX_AGE=0` + health checks in `settings.py`; redeploy. Retry once after a few seconds. |
| Migrations didn’t run | Render **Logs** → search for `migrate`; re-deploy or run `python manage.py migrate` in Shell. |

---

## Why saves sometimes fail until you refresh

On the **free** plan, two things sleep after ~5–15 minutes without traffic:

1. **Render** — your Django app spins down  
2. **Neon** — the database compute suspends  

When you submit a form, the app and DB must **wake up**. The first request can fail (timeout, closed connection) if Django reuses a connection Neon already closed. Refreshing works because everything is warm.

**What we did in code:** `CONN_MAX_AGE=0` and `CONN_HEALTH_CHECKS=True` so each request uses a fresh, verified connection.

**What you can do:**

- Wait 5–10 seconds after the first slow page load, then submit again  
- In Neon dashboard: **Project settings** → increase **Scale to zero** delay (paid plans can disable it)  
- Accept ~2–5 s delay after idle — or upgrade Neon/Render to stay always-on  

This is a platform limit, not lost data — your games are still in Neon once the save succeeds.

---

## Security

- Never commit `DATABASE_URL` to GitHub.  
- Only set it in Render **Environment** (and local `.env`).  
- Rotate the Neon password in the dashboard if the URL leaks.
