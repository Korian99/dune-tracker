"""Sync leader fields from live league data into bgc_uprising.py."""

import os
from copy import deepcopy
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from games.data.bgc_uprising import BGC_UPRISING_GAMES
from games.integrations.bgc.leader_sync import (
    fetch_league_from_worker,
    live_games_from_db,
    live_games_from_worker_league,
    merge_leaders_into_games,
)
from games.integrations.bgc.render import render_module


class Command(BaseCommand):
    help = (
        "Merge leader fields from live league data (Worker API or local DB) "
        "into games/data/bgc_uprising.py."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--league",
            default="liga-n0",
            help="League slug to read leaders from (default: liga-n0).",
        )
        source = parser.add_mutually_exclusive_group()
        source.add_argument(
            "--from-worker",
            action="store_true",
            help="Fetch live games from the Cloudflare Worker API.",
        )
        source.add_argument(
            "--from-db",
            action="store_true",
            help="Read live games from the local Django database.",
        )
        parser.add_argument(
            "--api-url",
            default=os.environ.get("DUNE_API_URL", ""),
            help="Worker base URL (default: DUNE_API_URL env).",
        )
        parser.add_argument(
            "--api-key",
            default=os.environ.get("DUNE_API_KEY", ""),
            help="API bearer token (default: DUNE_API_KEY env).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report leader updates without writing the module.",
        )
        parser.add_argument(
            "-o",
            "--output",
            default="games/data/bgc_uprising.py",
            help="Output Python module path.",
        )

    def handle(self, *args, **options):
        league_slug = options["league"]
        from_worker = options["from_worker"]
        from_db = options["from_db"]

        if not from_worker and not from_db:
            from_db = True

        if from_worker:
            api_url = (options["api_url"] or "").strip()
            api_key = (options["api_key"] or "").strip()
            if not api_url or not api_key:
                raise CommandError(
                    "Worker sync requires --api-url and --api-key "
                    "(or DUNE_API_URL and DUNE_API_KEY)."
                )
            try:
                league = fetch_league_from_worker(api_url, api_key, league_slug)
            except RuntimeError as exc:
                raise CommandError(str(exc)) from exc
            live_games = live_games_from_worker_league(league)
            source = f"Worker API ({api_url.rstrip('/')})"
        else:
            try:
                live_games = live_games_from_db(league_slug)
            except Exception as exc:
                raise CommandError(f"Could not load league {league_slug!r}: {exc}") from exc
            source = f"Django DB (league {league_slug})"

        games_data = deepcopy(BGC_UPRISING_GAMES)
        update_count, warnings = merge_leaders_into_games(games_data, live_games)

        self.stdout.write(
            f"Live games with import_key: {len(live_games)}; "
            f"leader fields updated: {update_count}"
        )
        for warning in warnings:
            self.stdout.write(self.style.WARNING(warning))

        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run — no file written."))
            return

        out = Path(options["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            render_module(games_data, source=source, leaders_synced=True),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(games_data)} game(s) to {out}"))
