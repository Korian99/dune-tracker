"""Canonical player display names when translating BGC backups."""

from __future__ import annotations

# BGC roster strings → names used in dune-tracker (Player.name / import JSON).
BGC_PLAYER_NAME_ALIASES: dict[str, str] = {
    "kori": "Kori",
    "matute": "Matías",
}


def normalize_bgc_player_name(name: str) -> str:
    """Map known BGC aliases to league roster names; preserve others as trimmed."""
    stripped = " ".join((name or "").split())
    if not stripped:
        return stripped
    canonical = BGC_PLAYER_NAME_ALIASES.get(stripped.casefold())
    return canonical if canonical is not None else stripped
