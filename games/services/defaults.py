"""Default league scoring — shared by models, migrations, and scoring logic."""

from typing import Any

DEFAULT_LEAGUE_SCORING_NOTES = """\
Puntos por partida:
• Puesto: 1.º = 5, 2.º = 3, 3.º = 2, 4.º = 1 (5.º o peor = 0).
• +1 si ganas antes de la ronda 7 (rondas 1–6 registradas).
• +1 si terminas con 10+ PV, +1 con 12+ PV, +1 con 15+ PV (se suman).
• Solo cuentan tus 8 mejores partidas hacia la clasificación.
"""


def default_league_scoring_config() -> dict[str, Any]:
    """Return a new dict (safe mutable copy for model defaults)."""
    return {
        "system": "standard",
        "count_games": 8,
        "placement_points": {"1": 5, "2": 3, "3": 2, "4": 1},
        "early_win_max_round": 6,
        "vp_thresholds": [10, 12, 15],
    }
