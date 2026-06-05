from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from .defaults import default_league_scoring_config


class Player(models.Model):
    """Registered player; may belong to one or more league rosters."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "player"
            slug = base
            n = 1
            qs = Player.objects.filter(slug=slug)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            while qs.exists():
                slug = f"{base}-{n}"
                n += 1
                qs = Player.objects.filter(slug=slug)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
            self.slug = slug
        super().save(*args, **kwargs)


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
        default=default_league_scoring_config,
        blank=True,
        help_text="Structured scoring JSON — see games/defaults.py and games/scoring.py",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    players = models.ManyToManyField(
        Player,
        through="LeagueMembership",
        related_name="leagues",
    )

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


class LeagueMembership(models.Model):
    """Player on a league roster."""

    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["player__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "player"],
                name="unique_league_player",
            ),
        ]

    def __str__(self):
        return f"{self.player.name} @ {self.league.name}"


class LeagueHito(models.Model):
    """
    League milestone / highscore track (Spanish UI: «Hito»).
    Built-in slugs: highscore, powerscore, lowscore; leagues can personalize names.
    """

    class Metric(models.TextChoices):
        AUTO_MAX_VP = "auto_max_vp", "Mayor PV (automático)"
        AUTO_MIN_VP = "auto_min_vp", "Menor PV (automático)"
        MANUAL = "manual", "Manual"

    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="hitos",
    )
    slug = models.SlugField(max_length=40)
    name = models.CharField(
        max_length=80,
        help_text="Display name (personalizable por liga).",
    )
    description = models.TextField(blank=True)
    metric = models.CharField(max_length=32, choices=Metric.choices)
    order = models.PositiveSmallIntegerField(default=0)
    is_builtin = models.BooleanField(
        default=False,
        help_text="True for highscore / powerscore / lowscore seeded on create.",
    )
    is_active = models.BooleanField(default=True)
    manual_value = models.CharField(
        max_length=120,
        blank=True,
        help_text="Powerscore: texto libre (p. ej. récord o nota de la liga).",
    )
    manual_player = models.ForeignKey(
        Player,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="powerscore_hitos",
        help_text="Legacy single holder; synced from manual_players when saving via UI.",
    )
    manual_players = models.ManyToManyField(
        Player,
        blank=True,
        related_name="powerscore_hitos_multi",
        help_text="Powerscore holders (supports ties).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "slug"]
        verbose_name = "league hito"
        verbose_name_plural = "league hitos"
        constraints = [
            models.UniqueConstraint(
                fields=["league", "slug"],
                name="unique_hito_slug_per_league",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.league.name})"


def resolve_player(name: str, league: League | None = None) -> Player:
    """
    Find or create a player by display name; add to league roster when league is set.
    """
    normalized = " ".join((name or "").split())
    if not normalized:
        raise ValueError("Player name is required")
    player, _ = Player.objects.get_or_create(
        name=normalized,
        defaults={"slug": ""},
    )
    if league:
        LeagueMembership.objects.get_or_create(league=league, player=player)
    return player


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
    tied_game = models.BooleanField(
        default=False,
        help_text="No single winner (VP tie acknowledged)",
    )
    designated_winner = models.ForeignKey(
        "GameResult",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="designated_win_for_game",
    )
    placement_tiebreaks = models.JSONField(
        default=dict,
        blank=True,
        help_text="Per-VP tiebreak: VP string -> 'tie', ordered [result pk, ...], or legacy winner pk",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-played_on", "-created_at"]

    def __str__(self):
        return f"Partida {self.played_on} ({self.get_base_game_display()})"

    def max_vp_results(self):
        """All results tied for highest VP in this game."""
        results = list(self.results.select_related("player"))
        if not results:
            return []
        max_vp = max(r.victory_points for r in results)
        return [r for r in results if r.victory_points == max_vp]

    def resolved_winner(self):
        """Single winner, or None if tie / unresolved multi-way tie."""
        if self.tied_game:
            return None
        if self.designated_winner_id:
            return self.designated_winner
        leaders = self.max_vp_results()
        if len(leaders) == 1:
            return leaders[0]
        return None

    @property
    def winner(self):
        return self.resolved_winner()

    @property
    def winner_summary(self):
        """Spanish one-line winner label for lists."""
        if self.tied_game:
            leaders = self.max_vp_results()
            if len(leaders) >= 2:
                names = ", ".join(r.player.name for r in leaders)
                return f"Empate ({names})"
            return "Empate"
        w = self.resolved_winner()
        if w:
            return f"{w.player.name} ({w.victory_points} PV)"
        leaders = self.max_vp_results()
        if len(leaders) >= 2:
            return "Empate sin resolver"
        return ""

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

    @property
    def notes_for_display(self):
        """Hide internal import markers from the game detail page."""
        notes = (self.notes or "").strip()
        if notes.startswith("import_key="):
            return ""
        return notes


class GameResult(models.Model):
    """Per-player outcome for one game."""

    ALLIANCE_FIELDS = (
        ("alliance_emperor", "Emperador"),
        ("alliance_guild", "Spacing Guild"),
        ("alliance_bene_gesserit", "Bene Gesserit"),
        ("alliance_fremen", "Fremen"),
    )

    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name="results",
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.PROTECT,
        related_name="game_results",
    )
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
                fields=["game", "player"],
                name="unique_player_per_game",
            ),
        ]

    def __str__(self):
        return f"{self.player.name} — {self.victory_points} PV"

    @property
    def placement(self):
        from .tiebreak import result_placement

        return result_placement(self)

    @property
    def is_winner(self):
        winner = self.game.resolved_winner()
        return winner is not None and winner.pk == self.pk

    @property
    def in_vp_tie(self):
        """True if this result shares the highest VP (for tie display)."""
        return self in self.game.max_vp_results()

    @property
    def alliances_held(self):
        return [label for field, label in self.ALLIANCE_FIELDS if getattr(self, field)]

    @property
    def sardaukar_label(self) -> str:
        """Spanish label for detail views."""
        count = self.sardaukar_count
        if count == 0:
            return "Ninguno"
        if count == 1:
            return "1 Sardaukar"
        return f"{count} Sardaukars"
