"""Rules for the league setup wizard. No views, no HTTP."""

from collections.abc import Iterator
from contextlib import contextmanager

import scheduler
from django.db import transaction

from league.models import Division, Event, Flight, Match, Team

STEPS: tuple[str, ...] = ("basics", "scoring", "flights", "teams", "games")
STEP_LABELS = {
    "basics": "Basics",
    "scoring": "Scoring",
    "flights": "Flights",
    "teams": "Teams",
    "games": "Games plan",
}


class SetupLocked(Exception):
    def __init__(self, message: str = (
        "Scores have been entered, so the setup is locked. "
        "Individual games can still be moved."
    )):
        super().__init__(message)


def active_teams(flight: Flight):
    return flight.teams.filter(withdrawn_at__isnull=True).order_by("pk")


def _games_per_team(times: int, n_teams: int) -> int:
    return times * (n_teams - 1 if n_teams % 2 == 0 else n_teams)


def default_plan(n_teams: int, weeks: int) -> str:
    if n_teams < 2:
        return "once"
    for plan, times in (("once", 1), ("twice", 2)):
        if _games_per_team(times, n_teams) >= weeks:
            return plan
    return "custom"


def effective_plan(flight: Flight, n_teams: int, weeks: int) -> str:
    return flight.games_plan or default_plan(n_teams, weeks)


def plan_grid(plan: str, n_teams: int, weeks: int, stored: list[int]) -> list[int]:
    if plan in ("once", "twice"):
        if n_teams < 2:
            return []
        try:
            return list(scheduler.round_robin_preset(n_teams, weeks, 1 if plan == "once" else 2))
        except scheduler.ScheduleError:
            return []
    if not stored:
        return [1] * weeks
    return (list(stored) + [0] * weeks)[:weeks]


def refresh_grids(event: Event) -> None:
    weeks = event.weeks.count()
    for flight in Flight.objects.filter(division__event=event):
        n = active_teams(flight).count()
        flight.games_per_team_by_week = plan_grid(
            effective_plan(flight, n, weeks), n, weeks, flight.games_per_team_by_week
        )
        flight.save(update_fields=["games_per_team_by_week"])


def set_weeks(event: Event, n: int) -> None:
    event.set_week_count(n)
    refresh_grids(event)


def mark_stale(event: Event) -> None:
    if Match.objects.filter(flight__division__event=event).exists():
        Event.objects.filter(pk=event.pk).update(schedule_stale=True)
        event.schedule_stale = True


def sync_flights(event: Event, cells: set[tuple[str, str]], confirm: bool) -> list[Flight]:
    existing = {
        (f.division.level, f.format): f
        for f in Flight.objects.filter(division__event=event).select_related("division")
    }
    doomed = [f for cell, f in existing.items() if cell not in cells]
    if not confirm:
        with_teams = [f for f in doomed if f.teams.exists()]
        if with_teams:
            return with_teams
    with transaction.atomic():
        for level, fmt in sorted(cells - existing.keys()):
            division, _ = Division.objects.get_or_create(event=event, level=level)
            Flight.objects.create(division=division, format=fmt, games_plan="")
        for flight in doomed:
            Match.objects.filter(flight=flight).delete()
            flight.delete()
        Division.objects.filter(event=event, flights__isnull=True).delete()
        if doomed:
            mark_stale(event)
    return []


def delete_team(team: Team) -> None:
    flight = team.flight
    event = flight.event
    with transaction.atomic():
        Match.objects.filter(flight=flight).delete()
        team.delete()
        mark_stale(event)
        refresh_grids(event)


def _flight_teams_ready(flight: Flight) -> bool:
    teams = list(active_teams(flight).prefetch_related("members"))
    return len(teams) >= 2 and all(len(t.members.all()) == 2 for t in teams)


def step_done(event: Event) -> dict[str, bool]:
    flights = list(Flight.objects.filter(division__event=event))
    weeks = event.weeks.count()
    extra = {
        "flights": bool(flights),
        "teams": bool(flights) and all(_flight_teams_ready(f) for f in flights),
        "games": bool(flights) and all(len(f.games_per_team_by_week) == weeks for f in flights),
    }
    return {
        step: event.setup_step >= i + 1 and extra.get(step, True)
        for i, step in enumerate(STEPS)
    }


def first_open_step(event: Event) -> str:
    done = step_done(event)
    return next((s for s in STEPS if not done[s]), "games")


@contextmanager
def editing(event: Event) -> Iterator[Event]:
    with transaction.atomic():
        locked = Event.objects.select_for_update().get(pk=event.pk)
        if locked.has_scores():
            raise SetupLocked()
        yield locked
