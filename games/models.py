from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify


class League(models.Model):
    """Groups games under shared rules; custom scoring applied via scoring_config later."""

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    scoring_notes = models.TextField(
        blank=True,
        help_text="League scoring rules (admin; user-facing copy is stored as entered).",
    )
    scoring_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured scoring JSON — see games/scoring.py",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "league"
            slug = base
            n = 1
            while League.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def game_count(self):
        return self.games.count()


class Game(models.Model):
    class BaseGame(models.TextChoices):
        UPRISING = "uprising", "Dune: Imperium — Uprising"
        IMPERIUM = "imperium", "Dune: Imperium (original)"

    class PlayerCount(models.IntegerChoices):
        TWO = 2, "2 jugadores"
        THREE = 3, "3 jugadores"
        FOUR = 4, "4 jugadores"
        SIX = 6, "6 jugadores (equipos)"

    league = models.ForeignKey(
        League,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="games",
    )
    played_on = models.DateField()
    base_game = models.CharField(
        max_length=20,
        choices=BaseGame.choices,
        default=BaseGame.UPRISING,
    )
    bloodlines = models.BooleanField(
        default=True,
        help_text="Bloodlines expansion was used",
    )
    player_count = models.PositiveSmallIntegerField(choices=PlayerCount.choices)
    rounds = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(30)],
        help_text="Number of rounds played",
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(600)],
        help_text="Total table time in minutes",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-played_on", "-created_at"]

    def __str__(self):
        return f"Partida {self.played_on} ({self.get_base_game_display()})"

    @property
    def winner(self):
        return self.results.order_by("-victory_points", "id").first()

    @property
    def formatted_duration(self):
        if not self.duration_minutes:
            return ""
        hours, minutes = divmod(self.duration_minutes, 60)
        if hours and minutes:
            return f"{hours} h {minutes} min"
        if hours:
            return f"{hours} h"
        return f"{minutes} min"


class GameResult(models.Model):
    """Per-player outcome for one game."""

    ALLIANCE_FIELDS = (
        ("alliance_emperor", "Emperador"),
        ("alliance_guild", "Gremio"),
        ("alliance_bene_gesserit", "Bene Gesserit"),
        ("alliance_fremen", "Fremen"),
    )

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="results",
    )
    player_name = models.CharField(max_length=80)
    leader = models.CharField(max_length=120, blank=True)
    victory_points = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(20)],
    )
    sardaukar_count = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(14)],
        help_text="Sardaukar commanders recruited (Bloodlines)",
    )
    alliance_emperor = models.BooleanField(default=False)
    alliance_guild = models.BooleanField(default=False)
    alliance_bene_gesserit = models.BooleanField(default=False)
    alliance_fremen = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["game", "player_name"],
                name="unique_player_per_game",
            ),
        ]

    def __str__(self):
        return f"{self.player_name} — {self.victory_points} PV"

    @property
    def placement(self):
        higher = self.game.results.filter(
            victory_points__gt=self.victory_points
        ).count()
        return higher + 1

    @property
    def is_winner(self):
        top = self.game.results.order_by("-victory_points", "id").first()
        return top and top.pk == self.pk

    @property
    def alliances_held(self):
        return [label for field, label in self.ALLIANCE_FIELDS if getattr(self, field)]
