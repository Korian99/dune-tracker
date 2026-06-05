# Self-host Dune Tracker at home with Cloudflare Tunnel

Guide for running **Dune Tracker** on your **home PC** (no corporate proxy) and exposing it with a **stable HTTPS URL** via Cloudflare — using your **mateousa** Cloudflare account.

**Why home PC:** `cloudflared` often fails on work networks (HTTP proxy, blocked UDP/TCP to Cloudflare). At home this usually works.

**Cost:** $0 for tunnel + local **SQLite** (no Render, no Neon). Your PC must be on for friends to use the site.

---

## What you need

| Item | Notes |
|------|--------|
| **Home PC** | Windows; stays on while the league uses the app |
| **Cloudflare account** | Log in as **mateousa** at [dash.cloudflare.com](https://dash.cloudflare.com) |
| **Domain on Cloudflare** | A hostname you control (e.g. `mateousa.com` or a subdomain). Add the domain to Cloudflare if it is not there yet |
| **Git** | Clone `dune-tracker` (or copy the project folder from your work PC) |
| **Python 3.11+** | Same as local dev |

---

## Part 1 — Prepare Dune Tracker (home PC)

### 1.1 Clone and install

```powershell
cd D:\Projects
git clone https://github.com/Korian99/dune-tracker.git
cd dune-tracker
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 1.2 `.env` for home self-host

Copy the example and edit (do **not** commit `.env`):

```powershell
copy .env.example .env
```

Use **local SQLite** — leave `DATABASE_URL` unset or commented:

```env
SECRET_KEY=paste-a-long-random-string-here
DEBUG=False

# Filled in after you create the public hostname (Part 2)
ALLOWED_HOSTS=127.0.0.1,localhost,dune.mateousa.com
CSRF_TRUSTED_ORIGINS=https://dune.mateousa.com

# Optional: migration 0011 creates admin on migrate
ADMIN_USER=your_admin_username
ADMIN_PASS=your_strong_password
```

Replace `dune.mateousa.com` with your real hostname (subdomain + domain on your mateousa account).

### 1.3 Database and static files

```powershell
py manage.py migrate
py manage.py collectstatic --noinput
```

Data lives in `db.sqlite3` in the project root. Back it up regularly (copy the file).

### 1.4 Run Django (terminal 1)

For a small group, this is enough:

```powershell
py manage.py runserver 127.0.0.1:8000
```

Optional sturdier server on Windows:

```powershell
pip install waitress
waitress-serve --listen=127.0.0.1:8000 config.wsgi:application
```

Leave this terminal open.

---

## Part 2 — Cloudflare Tunnel (mateousa account)

Log in to the **main** dashboard (not only Zero Trust):  
[https://dash.cloudflare.com](https://dash.cloudflare.com) — account **mateousa**.

### 2.1 Open Tunnels

Left sidebar:

**Networking** → **Tunnels**

If you do not see it, use the dashboard search bar and type **Tunnels**.

Direct link pattern (after login):

`https://dash.cloudflare.com/` → select account → **Networking** → **Tunnels**

Alternative (Zero Trust UI): **Networks** → **Connectors** → **Cloudflare Tunnels** at [one.dash.cloudflare.com](https://one.dash.cloudflare.com).

### 2.2 Create the tunnel

1. **Create a tunnel**
2. Name: `dune-tracker` (or any name)
3. Connector: **Cloudflared** → **Save tunnel**
4. **Choose environment:** Windows
5. Copy the **run command** (contains `--token eyJ...`)

### 2.3 Install `cloudflared` (once)

```powershell
winget install Cloudflare.cloudflared
```

Or download from:  
[https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/)

Check:

```powershell
cloudflared --version
```

### 2.4 Run the tunnel (terminal 2)

Paste the command from the dashboard, for example:

```powershell
cloudflared tunnel run --token eyJhIjoi...
```

Wait until the dashboard shows the tunnel as **Healthy** / connected.

### 2.5 Add a **Public Hostname** (important)

Do **not** use **Create route** with a **CIDR** like `127.0.0.1:8000`. That is for private networks + WARP, not for a public website.

In the tunnel configuration, add a **Public Hostname**:

| Field | Example |
|-------|---------|
| **Subdomain** | `dune` |
| **Domain** | `mateousa.com` (must be on this Cloudflare account) |
| **Path** | (leave empty) |
| **Type** | `HTTP` |
| **URL** | `localhost:8000` |

Result: `https://dune.mateousa.com` → your Django on port 8000.

Save.

### 2.6 Update `.env` with the real hostname

```env
ALLOWED_HOSTS=127.0.0.1,localhost,dune.mateousa.com
CSRF_TRUSTED_ORIGINS=https://dune.mateousa.com
DEBUG=False
```

Restart Django (terminal 1) after editing `.env`.

### 2.7 Test

On your phone (mobile data or home Wi‑Fi):

`https://dune.mateousa.com`

You should see Dune Tracker. Admin: `https://dune.mateousa.com/admin/` (user from `ADMIN_USER` / `ADMIN_PASS` after `migrate`).

---

## Part 3 — Run every game night

Open **two** terminals:

**Terminal 1 — Django**

```powershell
cd D:\Projects\dune-tracker
.\.venv\Scripts\activate
py manage.py runserver 127.0.0.1:8000
```

**Terminal 2 — Tunnel**

```powershell
cloudflared tunnel run --token eyJhIjoi...
```

(Use the same token command from the dashboard, or configure a named tunnel as a Windows service later.)

Share the `https://dune.mateousa.com` link with your league.

---

## Part 4 — Optional: start tunnel on boot

After it works manually:

1. Cloudflare dashboard → your tunnel → **Configure** → note tunnel name/ID
2. Run `cloudflared service install` with your token (see Cloudflare docs for Windows service)
3. Or create a Task Scheduler job that runs the `cloudflared tunnel run --token ...` command at logon

Django still needs its own terminal or service if you want the site up without logging in.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| **DisallowedHost** | Add exact hostname to `ALLOWED_HOSTS` (no `https://`) |
| **CSRF error on forms** | Set `CSRF_TRUSTED_ORIGINS=https://your-hostname` and `DEBUG=False` |
| **502 / tunnel error** | Django not running on `127.0.0.1:8000`, or wrong service URL in public hostname |
| **Static files missing** | Run `py manage.py collectstatic --noinput` |
| **Works on PC, not phone** | Check tunnel is Healthy; use HTTPS URL from public hostname |
| **Quick tunnel timeout** (`trycloudflare.com`) | Use **named tunnel + public hostname** on home network instead |
| **Work PC proxy** | Do not use work PC for tunnel; use this home setup only |

### Quick tunnel (temporary URL, no domain)

Only for quick tests on home Wi‑Fi:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Use the printed `https://….trycloudflare.com` URL. Add to `.env`:

```env
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost,.trycloudflare.com
```

URL changes every run — not for production.

---

## Backups

Copy `db.sqlite3` after sessions:

```powershell
copy db.sqlite3 backups\db-%date:~-4,4%%date:~-10,2%%date:~-7,2%.sqlite3
```

---

## If Cloudflare billing blocks Zero Trust

Some accounts ask for a $0 “purchase” and fail on payment. Try:

1. Add payment method under **Billing** on [dash.cloudflare.com](https://dash.cloudflare.com), then retry
2. Use **Networking → Tunnels** on the main dashboard (Feb 2026+ UI)
3. Open a **Billing** support ticket with Cloudflare
4. Fallback: **Tailscale** on home PC (private link, no public URL) — see [HOSTING.md](HOSTING.md)

---

## Summary

```
[Phone] --HTTPS--> Cloudflare edge --tunnel--> cloudflared (home PC) --> Django :8000 --> db.sqlite3
```

- **Account:** mateousa @ dash.cloudflare.com  
- **Tunnel UI:** Networking → Tunnels → Public Hostname → `HTTP` → `localhost:8000`  
- **Not:** CIDR route `127.0.0.1:8000`  
- **Run at home**, not on the work proxy network  

Related: [HOSTING.md](HOSTING.md) (Render/Neon), [NEON_SETUP.md](NEON_SETUP.md), [AGENTS.md](../AGENTS.md).
