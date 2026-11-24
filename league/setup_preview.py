"""Live per-flight summary for the wizard's games-plan step. Writes nothing."""

import dataclasses
from dataclasses import dataclass

import scheduler

from league.models import Event, Flight
from league.scheduling import event_flights
from league.setup import active_teams, effective_plan, plan_grid


@dataclass(frozen=True)
class FlightPlanView:
    flight: Flight
    team_count: int
    plan: str
    grid: list[int]
    total: int
    summary: str | None
    notes: list[str]
    blocker: str | None
    empty_weeks: list[int]


def _s(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _preset_error(plan: str, n: int, weeks: int) -> str:
    try:
        scheduler.round_robin_preset(n, weeks, 1 if plan == "once" else 2)
    except scheduler.ScheduleError as exc:
        return str(exc)
    return f"The {plan} plan doesn't fit {_s(weeks, 'week')}."


def plan_views(
    event: Event, overrides: dict[int, tuple[str, list[int]]] | None = None
) -> tuple[list[FlightPlanView], str | None]:
    overrides = overrides or {}
    weeks = event.weeks.count()
    flights = list(
        Flight.objects.filter(division__event=event)
        .select_related("division")
        .order_by("division__pk", "pk")
    )
    partial = []  # (flight, n, plan, grid, blocker, notes, empty_weeks)
    for flight in flights:
        teams = list(active_teams(flight).prefetch_related("members"))
        n = len(teams)
        if flight.pk in overrides:
            plan, stored = overrides[flight.pk]
        else:
            plan, stored = effective_plan(flight, n, weeks), flight.games_per_team_by_week
        grid = plan_grid(plan, n, weeks, list(stored))
        blocker = None
        if n < 2:
            blocker = f"Add at least 2 teams to {flight.name} before generating."
        else:
            bad = next((t for t in teams if not t.roster_ok()), None)
            if bad is not None:
                blocker = bad.roster_problem()
            elif not grid:
                blocker = _preset_error(plan, n, weeks)
        notes = []
        if n >= 2 and n % 2 == 1:
            notes.append(
                f"{n} teams: one team sits out each round, so each week one team "
                "plays 1 fewer. Byes rotate."
            )
        empty = [w for w, g in enumerate(grid, 1) if g == 0] if plan == "custom" else []
        partial.append((flight, n, plan, grid, blocker, notes, empty))

    ready = {
        str(p[0].pk): p[3] for p in partial if p[4] is None
    }
    summaries: dict[int, str] = {}
    error = None
    if ready:
        sched_flights = [
            dataclasses.replace(f, games_per_team_by_week=tuple(ready[f.id]))
            for f in event_flights(event)
            if f.id in ready
        ]
        try:
            schedule = scheduler.generate(sched_flights, event.courts)
        except scheduler.ScheduleError as exc:
            error = str(exc)
        else:
            report = scheduler.fairness_report(schedule, sched_flights)
            rounds: dict[int, int] = {}
            for m in schedule.matches:
                rounds[m.week] = max(rounds.get(m.week, 0), m.round_no)
            for sf in sched_flights:
                pk = int(sf.id)
                summaries[pk] = scheduler.summary_line(report, sf)
                ids = [t.id for t in sf.teams]
                long_notes = []
                for week in sorted(report.games_by_week):
                    g = max((report.games_by_week[week][t] for t in ids), default=0)
                    r = rounds.get(week, 0)
                    if g > 0 and r > g:
                        long_notes.append(
                            f"Week {week}: each team plays {_s(g, 'game')}. "
                            f"On {_s(event.courts, 'court')} that takes {r} rounds."
                        )
                for item in partial:
                    if item[0].pk == pk:
                        item[5].extend(long_notes)

    views = [
        FlightPlanView(
            flight=flight, team_count=n, plan=plan, grid=grid, total=sum(grid),
            summary=summaries.get(flight.pk), notes=notes, blocker=blocker,
            empty_weeks=empty,
        )
        for flight, n, plan, grid, blocker, notes, empty in partial
    ]
    return views, error
