import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.urls import reverse

from .models import Division, Event, Flight, Player, Team, TeamMember
from .setup import active_teams, effective_plan, plan_grid


class BasicsForm(forms.ModelForm):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    courts = forms.IntegerField(min_value=1, max_value=20)
    weeks = forms.IntegerField(min_value=1, max_value=20)

    class Meta:
        model = Event
        fields = ["name", "start_date", "courts"]

    field_order = ["name", "start_date", "weeks", "courts"]

    def __init__(self, *args, locked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["weeks"].initial = self.instance.weeks.count() if self.instance.pk else 4
        if not self.instance.pk:
            self.fields["courts"].initial = 2
        if locked:
            for name, field in self.fields.items():
                if name != "name":
                    field.disabled = True
            self.fields["weeks"].help_text = "Scores have been entered, so the weeks can't change."


class ScoringForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["match_format", "points_to_win", "win_by_two", "player_score_entry"]
        labels = {
            "match_format": "Match format",
            "points_to_win": "Points to win",
            "win_by_two": "Win by two",
            "player_score_entry": "Players can enter their own scores",
        }

    def __init__(self, *args, locked: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        if locked:
            for name, field in self.fields.items():
                if name != "player_score_entry":
                    field.disabled = True


def flight_cells() -> list[tuple[str, str]]:
    return [
        (f"{level}:{fmt}", f"{level_label} {fmt_label}")
        for level, level_label in Division.Level.choices
        for fmt, fmt_label in Flight.Format.choices
    ]


class FlightsForm(forms.Form):
    cells = forms.MultipleChoiceField(
        choices=flight_cells,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Pick at least one flight."},
    )
    confirm = forms.BooleanField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, event: Event, locked: bool = False, **kwargs):
        initial = {
            "cells": [
                f"{f.division.level}:{f.format}"
                for f in Flight.objects.filter(division__event=event).select_related("division")
            ]
        }
        super().__init__(*args, initial=initial, **kwargs)
        if locked:
            self.fields["cells"].disabled = True

    def selected(self) -> set[tuple[str, str]]:
        return {tuple(value.split(":")) for value in self.cleaned_data["cells"]}

    def grid(self) -> list[tuple[str, list]]:
        """Three rows of three checkboxes: Beginner/Intermediate/Advanced by Men's/Women's/Mixed."""
        boxes = list(self["cells"])
        width = len(Flight.Format.choices)
        return [
            (label, boxes[i * width : (i + 1) * width])
            for i, (_, label) in enumerate(Division.Level.choices)
        ]


def player_text(player: Player) -> str:
    """What a player field accepts and the type-ahead offers."""
    return f"{player.name} <{player.email}>" if player.email else f"{player.name} (#{player.pk})"


_PK_SUFFIX = re.compile(r"^(?P<name>.*?)\s*\(#(?P<pk>\d+)\)$")
_EMAIL_SUFFIX = re.compile(r"^(?P<name>.*?)\s*<(?P<email>[^<>]+)>$")


class TeamForm(forms.Form):
    name = forms.CharField(max_length=120)
    player1 = forms.CharField(max_length=200, label="Player 1")
    player1_email = forms.EmailField(required=False, label="Player 1 email (new players)")
    player2 = forms.CharField(max_length=200, label="Player 2")
    player2_email = forms.EmailField(required=False, label="Player 2 email (new players)")
    team = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, flight: Flight, team: Team | None = None, **kwargs):
        if team is not None and "initial" not in kwargs and not args:
            members = [m.player for m in team.members.select_related("player").order_by("pk")]
            kwargs["initial"] = {
                "name": team.name,
                "team": team.pk,
                **{f"player{i}": player_text(p) for i, p in enumerate(members[:2], 1)},
            }
        super().__init__(*args, **kwargs)
        self.flight = flight
        self.org = flight.event.organization
        self.team = team
        self.slots: list[tuple] = []
        search = reverse("player_search", args=[flight.event.pk])
        for field in ("player1", "player2"):
            self.fields[field].widget.attrs.update({
                "list": "player-options",
                "autocomplete": "off",
                "hx-get": search,
                "hx-trigger": "input changed delay:250ms",
                "hx-target": "#player-options",
                "hx-swap": "innerHTML",
            })

    def _resolve(self, field: str):
        """An existing Player, or ("new", name, email); None when the slot is ambiguous."""
        text = self.cleaned_data[field].strip()
        email_field = (self.cleaned_data.get(f"{field}_email") or "").strip()
        players = Player.objects.filter(organization=self.org)
        if match := _PK_SUFFIX.match(text):
            found = players.filter(pk=match["pk"]).first()
            if found:
                return found
            text = match["name"]
        elif match := _EMAIL_SUFFIX.match(text):
            email = match["email"].strip()
            try:
                validate_email(email)
            except ValidationError:
                self.add_error(field, "Enter a valid email address.")
                return None
            found = players.filter(email__iexact=email).first()
            return self._new(field, match["name"].strip(), email) if not found else found
        if not email_field:
            found = list(players.filter(name__iexact=text)[:2])
            if len(found) > 1:
                self.add_error(field, f"Two players are named {text}. Pick one from the list.")
                return None
            if found:
                return found[0]
            return self._new(field, text, "")
        taken = players.filter(email__iexact=email_field).first()
        if taken:
            self.add_error(
                field, f"{taken.name} <{taken.email}> already uses that email. Pick them from the list."
            )
            return None
        return self._new(field, text, email_field)

    def _new(self, field: str, name: str, email: str):
        if len(name) > 120:
            self.add_error(field, "Keep names to 120 characters.")
            return None
        return ("new", name, email)

    def clean(self):
        cleaned = super().clean()
        if self.errors.keys() & {"name", "player1", "player2"}:
            return cleaned
        name = cleaned["name"].strip()
        clash = self.flight.teams.filter(name__iexact=name)
        if self.team:
            clash = clash.exclude(pk=self.team.pk)
        if existing := clash.first():
            self.add_error("name", f"There's already a team called {existing.name} in this flight.")
        slots = [self._resolve("player1"), self._resolve("player2")]
        if None in slots:
            return cleaned
        a, b = slots
        if isinstance(a, tuple) and isinstance(b, tuple) and a[2] and a[2].lower() == b[2].lower()                 and a[1].lower() != b[1].lower():
            self.add_error("player2", f"Both players can't use {b[2]}.")
            return cleaned
        same = (
            isinstance(a, Player) and isinstance(b, Player) and a.pk == b.pk
            or isinstance(a, tuple) and isinstance(b, tuple)
            and (a[1].lower(), a[2].lower()) == (b[1].lower(), b[2].lower())
        )
        if same:
            self.add_error(None, "Pick two different players.")
            return cleaned
        for slot in slots:
            if not isinstance(slot, Player):
                continue
            membership = TeamMember.objects.filter(
                player=slot, team__in=active_teams(self.flight)
            ).select_related("team")
            if self.team:
                membership = membership.exclude(team=self.team)
            if other := membership.first():
                self.add_error(None, f"{slot.name} is already on {other.team.name} in this flight.")
        self.slots = slots
        return cleaned

    def save(self) -> Team:
        with transaction.atomic():
            players = [
                slot
                if isinstance(slot, Player)
                else Player.objects.create(organization=self.org, name=slot[1], email=slot[2])
                for slot in self.slots
            ]
            name = self.cleaned_data["name"].strip()
            if self.team:
                team = self.team
                team.name = name
                team.save(update_fields=["name"])
                team.members.exclude(player__in=players).delete()
            else:
                team = Team.objects.create(flight=self.flight, name=name)
            have = set(team.members.values_list("player_id", flat=True))
            for player in players:
                if player.pk not in have:
                    TeamMember.objects.create(team=team, player=player)
        return team


PLAN_OPTIONS = (("once", "once"), ("twice", "twice"), ("custom", "custom"))


class FlightGamesForm(forms.Form):
    """One flight's plan radio and, for the custom plan only, its per-week counts."""

    plan = forms.ChoiceField(choices=PLAN_OPTIONS, widget=forms.RadioSelect)

    def __init__(self, flight: Flight, weeks: int, data=None):
        self.flight = flight
        self.weeks = weeks
        prefix = f"f{flight.pk}"
        super().__init__(data, prefix=prefix, initial={"plan": self.resolved_plan()})
        # Week counts only matter (and are only checked) for the custom plan.
        if data is not None and data.get(f"{prefix}-plan") == "custom":
            for week in range(1, weeks + 1):
                self.fields[f"w{week}"] = forms.IntegerField(min_value=0, max_value=20)

    def resolved_plan(self) -> str:
        n = active_teams(self.flight).count()
        return effective_plan(self.flight, n, self.weeks)

    def override(self) -> tuple[str, list[int]]:
        plan = self.cleaned_data["plan"]
        if plan == "custom":
            return plan, [self.cleaned_data[f"w{w}"] for w in range(1, self.weeks + 1)]
        return plan, list(self.flight.games_per_team_by_week)


class GamesForm:
    """The games step: one sub-form per flight."""

    def __init__(self, event: Event, data=None):
        self.event = event
        weeks = event.weeks.count()
        flights = (
            Flight.objects.filter(division__event=event)
            .select_related("division__event__organization")
            .order_by("division__pk", "pk")
        )
        self.forms = [FlightGamesForm(f, weeks, data) for f in flights]
        self.bound = data is not None

    def is_valid(self) -> bool:
        return self.bound and all([f.is_valid() for f in self.forms])

    def overrides(self) -> dict[int, tuple[str, list[int]]]:
        return {f.flight.pk: f.override() for f in self.forms}

    def valid_overrides(self) -> dict[int, tuple[str, list[int]]]:
        """Overrides for previewing a partly bad form.

        A flight that failed validation but was posted as custom still previews as custom,
        with a best-effort grid (bad cells become 1), so its inputs and errors stay visible.
        """
        result = {}
        for f in self.forms:
            if not self.bound:
                continue
            if f.is_valid():
                result[f.flight.pk] = f.override()
            elif f.data.get(f"{f.prefix}-plan") == "custom":
                grid = []
                for week in range(1, f.weeks + 1):
                    try:
                        n = int(f.data.get(f"{f.prefix}-w{week}", ""))
                    except (TypeError, ValueError):
                        n = 1
                    grid.append(n if 0 <= n <= 20 else 1)
                result[f.flight.pk] = ("custom", grid)
        return result
