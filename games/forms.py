from django import forms
from django.forms import inlineformset_factory

from .models import Game, GameResult, League

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
    class Meta:
        model = League
        fields = ["name", "description", "scoring_notes"]
        labels = {
            "name": "Nombre",
            "description": "Descripción",
            "scoring_notes": "Reglas de puntuación",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "scoring_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Describe aquí el sistema de puntos de la liga…",
                }
            ),
        }


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
            "player_name",
            "leader",
            "victory_points",
            "sardaukar_count",
            "alliance_emperor",
            "alliance_guild",
            "alliance_bene_gesserit",
            "alliance_fremen",
        ]
        labels = {
            "player_name": "Jugador",
            "victory_points": "Puntos de victoria",
            "sardaukar_count": "Sardaukar",
            "alliance_emperor": "Emperador",
            "alliance_guild": "Gremio",
            "alliance_bene_gesserit": "Bene Gesserit",
            "alliance_fremen": "Fremen",
        }
        widgets = {
            "player_name": forms.TextInput(attrs={"placeholder": "Nombre"}),
            "victory_points": forms.NumberInput(attrs={"min": 0, "max": 20}),
            "sardaukar_count": forms.NumberInput(attrs={"min": 0, "max": 14}),
            "alliance_emperor": forms.CheckboxInput(),
            "alliance_guild": forms.CheckboxInput(),
            "alliance_bene_gesserit": forms.CheckboxInput(),
            "alliance_fremen": forms.CheckboxInput(),
        }


class BaseGameResultFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        active = [
            f
            for f in self.forms
            if f.cleaned_data
            and not f.cleaned_data.get("DELETE")
            and f.cleaned_data.get("player_name", "").strip()
        ]
        if len(active) < 2:
            raise forms.ValidationError(
                "Añade al menos dos jugadores con puntos de victoria."
            )

        for field, label in GameResult.ALLIANCE_FIELDS:
            holders = [
                f.cleaned_data.get("player_name", "").strip()
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
            if not form.cleaned_data.get("player_name", "").strip():
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
