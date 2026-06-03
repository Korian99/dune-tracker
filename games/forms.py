from django import forms
from django.forms import inlineformset_factory

from .models import Game, GameResult, League, Player, resolve_player
from .scoring import config_from_form_data, config_to_form_initial

LEADER_SUGGESTIONS = [
    "Paul Atreides",
    "Chani",
    "Gurney Halleck",
    "Staban Tuek",
    "Shaddam Corrino IV",
    "Irulan",
    "Baron Harkonnen",
    "Feyd-Rautha",
    "Lady Jessica",
    "Duncan Idaho",
    "Rabban",
    "Dr. Yueh",
    "Muad'Dib (Comandante)",
    "Emperador (Comandante)",
]


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
    vp_bonus_10 = forms.BooleanField(
        required=False,
        initial=True,
        label="+1 si alcanzas 10 PV",
    )
    vp_bonus_12 = forms.BooleanField(
        required=False,
        initial=True,
        label="+1 si alcanzas 12 PV",
    )
    vp_bonus_15 = forms.BooleanField(
        required=False,
        initial=True,
        label="+1 si alcanzas 15 PV",
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
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            initial = config_to_form_initial(self.instance.scoring_config or {})
            for key, value in initial.items():
                self.fields[key].initial = value

    def save(self, commit=True):
        league = super().save(commit=False)
        league.scoring_config = config_from_form_data(self.cleaned_data)
        if commit:
            league.save()
            self.save_m2m()
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
            "base_game",
            "bloodlines",
            "player_count",
            "rounds",
            "notes",
        ]
        labels = {
            "league": "Liga",
            "played_on": "Fecha",
            "base_game": "Juego base",
            "bloodlines": "Bloodlines",
            "player_count": "Número de jugadores",
            "rounds": "Rondas jugadas",
            "notes": "Notas",
        }
        widgets = {
            "played_on": forms.DateInput(attrs={"type": "date"}),
            "rounds": forms.NumberInput(
                attrs={"min": 1, "max": 30, "placeholder": "p. ej. 8"}
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "bloodlines": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["league"].required = False
        self.fields["league"].empty_label = "Sin liga (partida casual)"
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
        if "duration_minutes" in self.cleaned_data:
            instance.duration_minutes = self.cleaned_data["duration_minutes"]
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class GameResultForm(forms.ModelForm):
    player_pick = forms.CharField(
        label="Jugador",
        widget=forms.TextInput(
            attrs={
                "list": "roster-players",
                "placeholder": "Elige del plantel o escribe un nombre",
                "autocomplete": "off",
            }
        ),
    )
    leader = forms.CharField(
        required=False,
        label="Líder",
        widget=forms.TextInput(
            attrs={
                "list": "leader-suggestions",
                "placeholder": "Líder jugado",
            }
        ),
    )

    class Meta:
        model = GameResult
        fields = [
            "leader",
            "victory_points",
            "sardaukar_count",
            "alliance_emperor",
            "alliance_guild",
            "alliance_bene_gesserit",
            "alliance_fremen",
        ]
        labels = {
            "victory_points": "Puntos de victoria",
            "sardaukar_count": "Sardaukar",
            "alliance_emperor": "Emperador",
            "alliance_guild": "Gremio",
            "alliance_bene_gesserit": "Bene Gesserit",
            "alliance_fremen": "Fremen",
        }
        widgets = {
            "victory_points": forms.NumberInput(attrs={"min": 0, "max": 20}),
            "sardaukar_count": forms.NumberInput(attrs={"min": 0, "max": 14}),
            "alliance_emperor": forms.CheckboxInput(),
            "alliance_guild": forms.CheckboxInput(),
            "alliance_bene_gesserit": forms.CheckboxInput(),
            "alliance_fremen": forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        self.league = kwargs.pop("league", None)
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.player_id:
            self.fields["player_pick"].initial = self.instance.player.name

    def clean_player_pick(self):
        name = " ".join(self.cleaned_data.get("player_pick", "").split())
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
        return form.cleaned_data.get("player_pick", "").strip()

    def clean(self):
        super().clean()
        active = [
            f
            for f in self.forms
            if f.cleaned_data
            and not f.cleaned_data.get("DELETE")
            and self._player_label(f)
        ]
        if len(active) < 2:
            raise forms.ValidationError(
                "Añade al menos dos jugadores con puntos de victoria."
            )

        names = [self._player_label(f) for f in active]
        if len(names) != len(set(names)):
            raise forms.ValidationError(
                "Cada jugador solo puede aparecer una vez en la partida."
            )

        for field, label in GameResult.ALLIANCE_FIELDS:
            holders = [
                self._player_label(f)
                for f in active
                if f.cleaned_data.get(field)
            ]
            if len(holders) > 1:
                raise forms.ValidationError(
                    f"Solo un jugador puede tener la alianza {label} "
                    f"(seleccionados: {', '.join(holders)})."
                )

    def save(self, commit=True):
        if commit:
            for obj in self.deleted_objects:
                obj.delete()
        saved = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            if not self._player_label(form):
                continue
            saved.append(form.save(commit=commit))
        return saved


GameResultFormSet = inlineformset_factory(
    Game,
    GameResult,
    form=GameResultForm,
    formset=BaseGameResultFormSet,
    extra=3,
    max_num=6,
    can_delete=True,
)
