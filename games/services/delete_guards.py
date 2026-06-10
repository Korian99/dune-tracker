"""Block destructive actions when games or results would be orphaned."""

from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from games.models import GameResult, League, Player

MSG_LEAGUE_HAS_GAMES = (
    "No se puede eliminar una liga que tiene partidas registradas."
)
MSG_PLAYER_HAS_GAMES = (
    "No se puede eliminar un jugador con resultados en partidas."
)
MSG_ROSTER_PLAYER_HAS_LEAGUE_GAMES = (
    "No se puede quitar del plantel: el jugador tiene partidas en esta liga."
)


def ensure_league_can_delete(league: League) -> None:
    if league.games.exists():
        raise ValidationError(MSG_LEAGUE_HAS_GAMES)


def ensure_player_can_delete(player: Player) -> None:
    if player.game_results.exists():
        raise ValidationError(MSG_PLAYER_HAS_GAMES)


def ensure_league_roster_can_remove(league: League, player: Player) -> None:
    if GameResult.objects.filter(player=player, game__league=league).exists():
        raise ValidationError(MSG_ROSTER_PLAYER_HAS_LEAGUE_GAMES)


class LeagueMembershipInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        league = self.instance
        if not league or not league.pk:
            return
        for form in self.forms:
            if not form.cleaned_data or not form.cleaned_data.get("DELETE"):
                continue
            if form.instance.pk:
                ensure_league_roster_can_remove(league, form.instance.player)
