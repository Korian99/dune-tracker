from django import forms
from django.forms import inlineformset_factory

from games.models import Game, GameResult, League, Player, resolve_player
from games.services.leaders import LEADER_CHOICES
from games.services.scoring import (
    config_from_form_data,
    config_to_form_initial,
    format_vp_thresholds_display,
    parse_vp_thresholds_input,
)

ENHANCED_SELECT_CLASS = "enhanced-select"


def _enhanced_select_attrs(placeholder):
    return {"class": ENHANCED_SELECT_CLASS, "data-placeholder": placeholder}


def _player_choices(league=None):
    """Players available when logging a game."""
    if league:
        names = list(
            league.players.order_by("name").values_list("name", flat=True)
        )
    else:
        names = list(Player.objects.order_by("name").values_list("name", flat=True))
    choices = [("", "— Elige jugador —")]
    choices.extend((n, n) for n in names)
    return choices


def _player_choice_list(league=None):
    """Names only, for alliance assignment."""
    if league:
        return list(league.players.order_by("name").values_list("name", flat=True))
    return list(Player.objects.order_by("name").values_list("name", flat=True))


class LeagueForm(forms.ModelForm):
    count_games = forms.IntegerField(
        min_value=0,
        max_value=99,
        initial=8,
        label="Partidas que cuentan",
        help_text="Solo las mejores N puntuaciones suman (0 = todas).",
    )
    points_1st = forms.IntegerField(min_value=0, max_value=20, initial=5, label="Puntos 1.º")
    points_2nd = forms.IntegerField(min_value=0, max_value=20, initial=3, label="Puntos 2.º")
    points_3rd = forms.IntegerField(min_value=0, max_value=20, initial=2, label="Puntos 3.º")
    points_4th = forms.IntegerField(min_value=0, max_value=20, initial=1, label="Puntos 4.º")
    early_win_max_round = forms.IntegerField(
        min_value=0,
        max_value=30,
        initial=6,
        label="Victoria temprana hasta ronda",
        help_text="+1 si ganas con rondas 1..N (0 = desactivado). Ej. 6 = antes de ronda 7.",
    )
    vp_thresholds = forms.CharField(
        required=False,
        initial="10, 12, 15",
        label="Umbrales de PV para bonos",
        help_text=(
            "+1 por cada umbral alcanzado (acumulable). Separa con comas, "
            "ej. 10, 12, 15. Vacío = sin bonos por PV."
        ),
        widget=forms.TextInput(
            attrs={
                "class": "vp-thresholds-input",
                "placeholder": "10, 12, 15",
                "spellcheck": "false",
                "inputmode": "numeric",
            }
        ),
    )

    class Meta:
        model = League
        fields = ["name", "description", "scoring_notes"]
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "scoring_notes": "Reglas (texto para jugadores)",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "scoring_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Reglas de puntuación de la liga…",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        from games.services.hitos import powerscore_hito

        super().__init__(*args, **kwargs)
        if self.instance.pk:
            initial = config_to_form_initial(self.instance.scoring_config or {})
            for key, value in initial.items():
                self.fields[key].initial = value
            roster = list(self.instance.players.order_by("name").values_list("name", flat=True))
            ps = powerscore_hito(self.instance)
            self.fields["powerscore_value"] = forms.CharField(
                required=False,
                max_length=120,
                label="Powerscore",
                help_text="Récord manual de la liga (texto libre).",
                initial=ps.manual_value if ps else "",
            )
            initial_players: list[str] = []
            if ps:
                initial_players = list(
                    ps.manual_players.order_by("name").values_list("name", flat=True)
                )
                if not initial_players and ps.manual_player_id:
                    initial_players = [ps.manual_player.name]
            self.fields["powerscore_players"] = forms.MultipleChoiceField(
                required=False,
                label="Jugadores (empate)",
                choices=[(n, n) for n in roster],
                widget=forms.CheckboxSelectMultiple,
                help_text="Marca todos los que comparten el récord.",
                initial=initial_players,
            )

    def clean_vp_thresholds(self):
        raw = self.cleaned_data.get("vp_thresholds", "")
        try:
            parsed = parse_vp_thresholds_input(raw)
        except ValueError as exc:
            raise forms.ValidationError(f"ERROR — {exc}") from exc
        self.cleaned_data["_vp_thresholds_parsed"] = parsed
        return format_vp_thresholds_display(parsed)

    def save(self, commit=True):
        from games.services.hitos import ensure_default_hitos, powerscore_hito

        league = super().save(commit=False)
        league.scoring_config = config_from_form_data(self.cleaned_data)
        if commit:
            is_new = league.pk is None
            league.save()
            self.save_m2m()
            if is_new:
                ensure_default_hitos(league)
            elif "powerscore_value" in self.cleaned_data:
                ps = powerscore_hito(league)
                if ps:
                    ps.manual_value = self.cleaned_data.get("powerscore_value", "")
                    player_names = self.cleaned_data.get("powerscore_players", [])
                    players = [
                        resolve_player(name, league=league) for name in player_names
                    ]
                    ps.manual_players.set(players)
                    ps.manual_player = players[0] if players else None
                    ps.save(update_fields=["manual_value", "manual_player"])
        return league


class LeagueAddPlayerForm(forms.Form):
    name = forms.CharField(
        max_length=80,
        label="Nombre del jugador",
        widget=forms.TextInput(attrs={"placeholder": "Nombre"}),
    )

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Introduce un nombre.")
        return name

    def save(self, league: League) -> Player:
        return resolve_player(self.cleaned_data["name"], league=league)


class GameForm(forms.ModelForm):
    duration_hours = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=10,
        label="Horas",
        widget=forms.NumberInput(attrs={"min": 0, "placeholder": "0"}),
    )
    duration_minutes_part = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=59,
        label="Minutos",
        widget=forms.NumberInput(attrs={"min": 0, "max": 59, "placeholder": "0"}),
    )

    class Meta:
        model = Game
        fields = [
            "league",
            "played_on",
            "player_count",
            "rounds",
            "notes",
        ]
        labels = {
            "league": "Liga",
            "played_on": "Fecha",
            "player_count": "Número de jugadores",
            "rounds": "Rondas jugadas",
            "notes": "Notas",
        }
        widgets = {
            "played_on": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
            "rounds": forms.NumberInput(
                attrs={"min": 1, "max": 30, "placeholder": "p. ej. 8"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["league"].required = False
        self.fields["league"].empty_label = "Sin liga (partida casual)"
        self.fields["played_on"].input_formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%y",
        ]
        if not self.instance.pk:
            self.fields["player_count"].initial = Game.PlayerCount.FOUR
        if self.instance.pk and self.instance.duration_minutes:
            hours, minutes = divmod(self.instance.duration_minutes, 60)
            self.fields["duration_hours"].initial = hours
            self.fields["duration_minutes_part"].initial = minutes

    def clean(self):
        cleaned = super().clean()
        hours = cleaned.get("duration_hours")
        minutes = cleaned.get("duration_minutes_part")
        if hours is None and minutes is None:
            return cleaned
        hours = hours or 0
        minutes = minutes or 0
        if hours == 0 and minutes == 0:
            cleaned["duration_minutes"] = None
        else:
            total = hours * 60 + minutes
            if total < 1:
                raise forms.ValidationError(
                    "La duración debe ser de al menos 1 minuto."
                )
            cleaned["duration_minutes"] = total
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.base_game = Game.BaseGame.UPRISING
        instance.bloodlines = True
        if "duration_minutes" in self.cleaned_data:
            instance.duration_minutes = self.cleaned_data["duration_minutes"]
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class GameAllianceForm(forms.Form):
    """One alliance holder per faction for the whole game."""

    alliance_emperor = forms.ChoiceField(
        required=False,
        label="Emperador",
        choices=[],
        widget=forms.Select(attrs=_enhanced_select_attrs("Nadie")),
    )
    alliance_guild = forms.ChoiceField(
        required=False,
        label="Spacing Guild",
        choices=[],
        widget=forms.Select(attrs=_enhanced_select_attrs("Nadie")),
    )
    alliance_bene_gesserit = forms.ChoiceField(
        required=False,
        label="Bene Gesserit",
        choices=[],
        widget=forms.Select(attrs=_enhanced_select_attrs("Nadie")),
    )
    alliance_fremen = forms.ChoiceField(
        required=False,
        label="Fremen",
        choices=[],
        widget=forms.Select(attrs=_enhanced_select_attrs("Nadie")),
    )

    def __init__(self, *args, player_names=None, initial_assignments=None, **kwargs):
        super().__init__(*args, **kwargs)
        names = {n.strip() for n in (player_names or []) if n and n.strip()}
        if initial_assignments:
            for holder in initial_assignments.values():
                if holder and holder.strip():
                    names.add(holder.strip())
        if self.is_bound:
            for field_name, _label in GameResult.ALLIANCE_FIELDS:
                val = (self.data.get(field_name) or "").strip()
                if val:
                    names.add(val)
        names = sorted(names)
        choices = [("", "— Nadie —")] + [(n, n) for n in names]
        for field in self.fields.values():
            field.choices = choices
        if initial_assignments and not self.is_bound:
            for field_name, holder in initial_assignments.items():
                if field_name in self.fields and holder:
                    self.fields[field_name].initial = holder

class GameResultForm(forms.ModelForm):
    player_pick = forms.ChoiceField(
        label="Jugador",
        choices=[],
        widget=forms.Select(attrs=_enhanced_select_attrs("Elige jugador…")),
    )
    leader = forms.ChoiceField(
        required=False,
        label="Líder",
        choices=LEADER_CHOICES,
        widget=forms.Select(attrs=_enhanced_select_attrs("Elige líder…")),
    )

    class Meta:
        model = GameResult
        fields = [
            "leader",
            "victory_points",
            "sardaukar_count",
        ]
        labels = {
            "victory_points": "Puntos de victoria",
            "sardaukar_count": "Sardaukar",
        }
        widgets = {
            "victory_points": forms.NumberInput(attrs={"min": 0, "max": 20}),
            "sardaukar_count": forms.NumberInput(attrs={"min": 0, "max": 14}),
        }

    def __init__(self, *args, **kwargs):
        self.league = kwargs.pop("league", None)
        super().__init__(*args, **kwargs)
        self.fields["player_pick"].choices = _player_choices(self.league)
        if self.instance.pk and self.instance.player_id:
            self.fields["player_pick"].initial = self.instance.player.name
        if self.instance.pk and self.instance.leader:
            self.fields["leader"].initial = self.instance.leader

    def clean_player_pick(self):
        name = self.cleaned_data.get("player_pick", "").strip()
        if not name:
            return ""
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        name = self.cleaned_data.get("player_pick", "")
        if name:
            instance.player = resolve_player(name, league=self.league)
        if commit:
            instance.save()
        return instance


class BaseGameResultFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.league = kwargs.pop("league", None)
        form_kwargs = kwargs.pop("form_kwargs", None) or {}
        form_kwargs.setdefault("league", self.league)
        kwargs["form_kwargs"] = form_kwargs
        super().__init__(*args, **kwargs)

    def _player_label(self, form):
        return (form.cleaned_data.get("player_pick") or "").strip()

    def active_player_names(self):
        return [self._player_label(f) for f in self.forms if self._player_label(f)]

    def _active_forms(self):
        return [
            f
            for f in self.forms
            if f.cleaned_data
            and not f.cleaned_data.get("DELETE")
            and self._player_label(f)
        ]

    def clean(self):
        super().clean()
        active = self._active_forms()
        if len(active) < 2:
            raise forms.ValidationError(
                "Añade al menos dos jugadores con puntos de victoria."
            )

        names = [self._player_label(f) for f in active]
        if len(names) != len(set(names)):
            raise forms.ValidationError(
                "Cada jugador solo puede aparecer una vez en la partida."
            )


GameResultFormSet = inlineformset_factory(
    Game,
    GameResult,
    form=GameResultForm,
    formset=BaseGameResultFormSet,
    extra=4,
    max_num=6,
    can_delete=True,
)
