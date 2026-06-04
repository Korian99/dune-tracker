"""
Create or update Django admin from ADMIN_USER / ADMIN_PASS (username only; no email).

Reads os.environ after loading project .env when present (local dev).
On Render, set the same variables in the service Environment tab (no .env file).
"""

import os
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.db import migrations


def _load_project_dotenv() -> None:
    """Load BASE_DIR/.env without requiring Django settings (stdlib fallback)."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    env_path = base_dir / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except ImportError:
        pass
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def create_admin_from_env(apps, schema_editor):
    _load_project_dotenv()
    username = (os.environ.get("ADMIN_USER") or "").strip()
    password = (os.environ.get("ADMIN_PASS") or "").strip()
    if not username or not password:
        return

    User = apps.get_model("auth", "User")

    user = User.objects.filter(username=username).first()
    if user is None:
        User.objects.create(
            username=username,
            email="",
            password=make_password(password),
            is_staff=True,
            is_superuser=True,
        )
        return

    user.password = make_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.save(update_fields=["password", "is_staff", "is_superuser", "is_active"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0010_league_hito_manual_players"),
    ]

    operations = [
        migrations.RunPython(create_admin_from_env, noop_reverse),
    ]
