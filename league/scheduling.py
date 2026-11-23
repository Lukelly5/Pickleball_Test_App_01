"""Bridge between the Django models and the pure-Python `scheduler` package."""

from collections import Counter

import scheduler
from django.db import transaction
from django.db.models import Prefetch

from league.models import Event, Flight, Match, Team, TeamMember, Week


def _player_keys(event: Event) -> dict[int, str]:
    """Map Player pk -> scheduler player key. Names shared by different
    players in the event become "<name> (#<pk>)"."""
    players = {
        m.player_id: m.player.name
        for m in TeamMember.objects.filter(team__flight__division__event=event).select_related(
            "player"
        )
    }
    counts = Counter(players.values())
    return {
        pk: name if counts[name] == 1 else f"{name} (#{pk})" for pk, name in players.items()
    }


def event_flights(event: Event, include_withdrawn: bool = False) -> list[scheduler.Flight]:
    keys = _player_keys(event)
    members = Prefetch(
        "members", queryset=TeamMember.objects.order_by("pk").select_related("player")
    )
    teams = Team.objects.order_by("pk").prefetch_related(members)
    if not include_withdrawn:
        teams = teams.filter(withdrawn_at__isnull=True)
    flights = (
        Flight.objects.filter(division__event=event)
        .select_related("division")
        .prefetch_related(Prefetch("teams", queryset=teams))
        .order_by("division__pk", "pk")
    )
    return [
        scheduler.Flight(
            id=str(flight.pk),
            name=flight.name,
            teams=tuple(
                scheduler.Team(
                    id=str(team.pk),
                    name=team.name,
                    players=tuple(keys[m.player_id] for m in team.members.all()),
                )
                for team in flight.teams.all()
            ),
            games_per_team_by_week=tuple(flight.games_per_team_by_week),
        )
        for flight in flights
    ]


def _weeks(n: int) -> str:
    return f"{n} week" if n == 1 else f"{n} weeks"


def _check_ready(event: Event) -> None:
    flights = list(
        Flight.objects.filter(division__event=event)
        .select_related("division")
        .order_by("division__pk", "pk")
    )
    if not flights:
        raise scheduler.ScheduleError("Add at least one flight before generating.")
    if event.has_scores():
        raise scheduler.ScheduleError(
            "Scores have been entered, so the schedule can't be regenerated. "
            "Move individual games instead."
        )
    for team in Team.objects.filter(
        flight__division__event=event, withdrawn_at__isnull=True
    ).order_by("flight__division__pk", "flight__pk", "pk"):
        if team.members.count() != 2:
            raise scheduler.ScheduleError(
                f"{team.name} needs exactly 2 players before generating."
            )
    for flight in flights:
        games = flight.games_per_team_by_week
        if not isinstance(games, list) or not all(
            type(g) is int and g >= 0 for g in games
        ):
            raise scheduler.ScheduleError(f"{flight.name} has an invalid games-per-team list.")
    numbers = sorted(event.weeks.values_list("number", flat=True))
    weeks = len(numbers)
    for flight in flights:
        if len(flight.games_per_team_by_week) != weeks:
            raise scheduler.ScheduleError(
                f"{flight.name} has games for {_weeks(len(flight.games_per_team_by_week))} "
                f"but the event has {_weeks(weeks)}."
            )
    if numbers != list(range(1, weeks + 1)):
        raise scheduler.ScheduleError(
            f"{event.name}'s weeks must be numbered 1 to {weeks} with none missing."
        )


def generate_event(event: Event) -> scheduler.Schedule:
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=event.pk)
        _check_ready(event)
        schedule = scheduler.generate(event_flights(event), event.courts)
        weeks = {w.number: w for w in Week.objects.filter(event=event)}
        Match.objects.filter(flight__division__event=event).delete()
        Match.objects.bulk_create(
            Match(
                flight_id=int(m.flight_id),
                week=weeks[m.week],
                round_no=m.round_no,
                court_no=m.court_no,
                team_a_id=int(m.team_a.id),
                team_b_id=int(m.team_b.id),
            )
            for m in schedule.matches
        )
        Event.objects.filter(pk=event.pk).update(schedule_stale=False)
    return schedule


def load_schedule(event: Event) -> tuple[scheduler.Schedule, list[scheduler.Flight]]:
    flights = event_flights(event, include_withdrawn=True)
    teams = {t.id: t for f in flights for t in f.teams}
    rows = Match.objects.filter(
        flight__division__event=event,
        status__in=[Match.Status.SCHEDULED, Match.Status.FINAL],
    ).select_related("week")
    matches = tuple(
        scheduler.Match(
            flight_id=str(row.flight_id),
            week=row.week.number,
            round_no=row.round_no,
            court_no=row.court_no,
            team_a=teams[str(row.team_a_id)],
            team_b=teams[str(row.team_b_id)],
        )
        for row in rows
    )
    return scheduler.Schedule(matches, event.courts), flights
