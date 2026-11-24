import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

# 7 days is an assumption; the PRD does not say how long an invite lasts.
INVITE_TTL = timedelta(days=7)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def invite_expiry() -> datetime:
    return timezone.now() + INVITE_TTL


class Player(models.Model):
    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="players"
    )
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="player",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=~models.Q(email=""),
                name="unique_player_email_per_org",
            )
        ]

    def __str__(self):
        return self.name


class Invite(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        PLAYER = "player", "Player"

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE)
    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=new_token)
    role = models.CharField(max_length=10, choices=Role.choices)
    player = models.ForeignKey(Player, null=True, blank=True, on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=invite_expiry)
    accepted_at = models.DateTimeField(null=True, blank=True)

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or timezone.now()) >= self.expires_at

    def __str__(self):
        return f"Invite for {self.email}"


class Event(models.Model):
    class Type(models.TextChoices):
        LEAGUE = "league", "League"
        TOURNAMENT = "tournament", "Tournament"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        COMPLETED = "completed", "Completed"

    class MatchFormat(models.TextChoices):
        SINGLE = "single", "1 game"
        BEST_OF_3 = "best_of_3", "Best of 3"
        BEST_OF_5 = "best_of_5", "Best of 5"

    class PointsToWin(models.IntegerChoices):
        ELEVEN = 11, "11"
        FIFTEEN = 15, "15"
        TWENTY_ONE = 21, "21"

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="events"
    )
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=12, choices=Type.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    start_date = models.DateField()
    courts = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    match_format = models.CharField(
        max_length=12, choices=MatchFormat.choices, default=MatchFormat.SINGLE
    )
    points_to_win = models.IntegerField(
        choices=PointsToWin.choices, default=PointsToWin.ELEVEN
    )
    win_by_two = models.BooleanField(default=True)
    player_score_entry = models.BooleanField(default=False)
    share_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    window_minutes = models.PositiveIntegerField(null=True, blank=True)
    game_minutes = models.PositiveIntegerField(null=True, blank=True)
    schedule_stale = models.BooleanField(default=False)
    setup_step = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "-id"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.type == self.Type.TOURNAMENT:
            if not self.window_minutes:
                raise ValidationError(
                    {"window_minutes": "A tournament needs a time window in minutes."}
                )
            if not self.game_minutes:
                self.game_minutes = 15

    def has_scores(self) -> bool:
        """True once any match is final, forfeited, or has a game score."""
        matches = Match.objects.filter(flight__division__event=self)
        return (
            matches.filter(
                models.Q(status=Match.Status.FINAL) | models.Q(forfeited_by__isnull=False)
            ).exists()
            or GameScore.objects.filter(match__flight__division__event=self).exists()
        )

    def set_week_count(self, n: int) -> None:
        """Make this event's weeks exactly 1..n, each dated a week apart."""
        with transaction.atomic():
            # Lock the row so the score check and the writes can't interleave with a score save.
            locked = Event.objects.select_for_update().get(pk=self.pk)
            if locked.has_scores():
                raise ValidationError("Scores have been entered, so the weeks can't change.")
            self.weeks.filter(number__gt=n).delete()
            weeks = {w.number: w for w in self.weeks.all()}
            for number in range(1, n + 1):
                day = self.start_date + timedelta(days=7 * (number - 1))
                if number in weeks:
                    weeks[number].date = day
                else:
                    weeks[number] = Week(event=self, number=number, date=day)
            Week.objects.bulk_create(w for w in weeks.values() if w.pk is None)
            Week.objects.bulk_update([w for w in weeks.values() if w.pk is not None], ["date"])


class Division(models.Model):
    class Level(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="divisions")
    level = models.CharField(max_length=12, choices=Level.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "level"], name="unique_division_level")
        ]

    def __str__(self):
        return f"{self.event.name}: {self.get_level_display()}"


class Flight(models.Model):
    class Format(models.TextChoices):
        MENS = "mens", "Men's"
        WOMENS = "womens", "Women's"
        MIXED = "mixed", "Mixed"

    class Plan(models.TextChoices):
        AUTO = "", "Not chosen"
        ONCE = "once"
        TWICE = "twice"
        CUSTOM = "custom"

    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name="flights")
    format = models.CharField(max_length=10, choices=Format.choices)
    games_plan = models.CharField(
        max_length=6, choices=Plan.choices, blank=True, default=Plan.CUSTOM
    )
    games_per_team_by_week = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["division", "format"], name="unique_flight_format")
        ]

    @property
    def event(self) -> Event:
        return self.division.event

    @property
    def name(self) -> str:
        return f"{self.division.get_level_display()} {self.get_format_display()}"

    def __str__(self):
        return self.name

    def clean(self):
        games = self.games_per_team_by_week
        if not isinstance(games, list) or any(
            isinstance(g, bool) or not isinstance(g, int) or g < 0 for g in games
        ):
            raise ValidationError(
                {
                    "games_per_team_by_week": (
                        f"Games per team for {self.name} must be a list of whole "
                        "numbers, zero or more."
                    )
                }
            )


class Team(models.Model):
    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name="teams")
    name = models.CharField(max_length=120)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    players = models.ManyToManyField(Player, through="TeamMember", related_name="teams")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["flight", "name"], name="unique_team_name_per_flight")
        ]

    def __str__(self):
        return self.name

    def roster_ok(self) -> bool:
        """Players are optional: a team names both of its players or none of them."""
        return len(self.members.all()) in (0, 2)

    def roster_problem(self) -> str | None:
        if self.roster_ok():
            return None
        return f"{self.name} has only 1 player. Add a second player, or remove both, before generating."


class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    player = models.ForeignKey(Player, on_delete=models.RESTRICT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["team", "player"], name="unique_team_member")
        ]

    def __str__(self):
        return f"{self.player} on {self.team}"

    def clean(self):
        if not self.team_id or not self.player_id:
            return
        others = TeamMember.objects.filter(team_id=self.team_id).exclude(pk=self.pk)
        if others.count() >= 2:
            raise ValidationError(f"Team {self.team.name} already has two players.")
        if self.player.organization_id != self.team.flight.event.organization_id:
            raise ValidationError(
                f"{self.player.name} belongs to a different organization than "
                f"team {self.team.name}."
            )


class Week(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELLED = "cancelled", "Cancelled"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="weeks")
    number = models.PositiveSmallIntegerField()
    date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["event", "number"], name="unique_week_number")
        ]

    def __str__(self):
        return f"{self.event.name} Week {self.number}"


class Match(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        FINAL = "final", "Final"
        CANCELLED = "cancelled", "Cancelled"
        VOID = "void", "Void"

    flight = models.ForeignKey(Flight, on_delete=models.CASCADE, related_name="matches")
    week = models.ForeignKey(Week, on_delete=models.CASCADE, related_name="matches")
    round_no = models.PositiveSmallIntegerField()
    court_no = models.PositiveSmallIntegerField()
    team_a = models.ForeignKey(Team, on_delete=models.RESTRICT, related_name="+")
    team_b = models.ForeignKey(Team, on_delete=models.RESTRICT, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    winner = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.RESTRICT, related_name="+"
    )
    forfeited_by = models.ForeignKey(
        Team, null=True, blank=True, on_delete=models.RESTRICT, related_name="+"
    )
    last_edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["week__number", "round_no", "court_no"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(team_a=models.F("team_b")), name="match_distinct_teams"
            ),
            models.CheckConstraint(
                condition=models.Q(round_no__gte=1), name="match_round_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(court_no__gte=1), name="match_court_positive"
            ),
            models.UniqueConstraint(
                fields=["week", "round_no", "court_no"], name="one_match_per_court_per_round"
            ),
        ]

    def __str__(self):
        return (
            f"Wk {self.week.number} R{self.round_no} C{self.court_no}: "
            f"{self.team_a} v {self.team_b}"
        )

    def clean(self):
        if not (self.flight_id and self.week_id):
            return
        if self.week.event_id != self.flight.event.pk:
            raise ValidationError(
                f"Week {self.week.number} is not part of the event for {self.flight.name}."
            )
        for field in ("team_a", "team_b"):
            team = getattr(self, field) if getattr(self, f"{field}_id") else None
            if team is not None and team.flight_id != self.flight_id:
                raise ValidationError(
                    f"Team {team.name} is not in the {self.flight.name} flight."
                )
        in_match = {self.team_a_id, self.team_b_id}
        for field, label in (("winner", "winner"), ("forfeited_by", "forfeiting team")):
            team_id = getattr(self, f"{field}_id")
            if team_id is not None and team_id not in in_match:
                raise ValidationError(
                    f"The {label} must be one of the two teams in this match."
                )


class GameScore(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="games")
    game_no = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    points_a = models.PositiveSmallIntegerField()
    points_b = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["game_no"]
        constraints = [
            models.UniqueConstraint(fields=["match", "game_no"], name="unique_game_no_per_match")
        ]

    def __str__(self):
        return f"Game {self.game_no}: {self.points_a}-{self.points_b}"
