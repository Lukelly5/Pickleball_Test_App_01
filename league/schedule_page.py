"""State for the read-only Schedule tab: which week, filters, and Tonight mode."""

from dataclasses import dataclass
from datetime import date

from django.http import QueryDict

from league.filters import read_filters, to_int
from league.models import Event, Week


@dataclass(frozen=True)
class ScheduleState:
    week: int | None  # None: the event has no weeks, or Tonight with no game today
    division: str
    flight: int | None
    tonight: bool


@dataclass(frozen=True)
class WeekPill:
    number: int
    label: str
    cancelled: bool


def _live(week: Week) -> bool:
    return week.status != Week.Status.CANCELLED


def tonight_week(weeks: list[Week], today: date) -> Week | None:
    return next((w for w in weeks if w.date == today and _live(w)), None)


def next_game_night(weeks: list[Week], today: date) -> Week | None:
    later = [w for w in weeks if w.date is not None and w.date > today and _live(w)]
    return min(later, key=lambda w: w.date, default=None)


def default_week(weeks: list[Week], today: date) -> int | None:
    if not weeks:
        return None
    tonight = tonight_week(weeks, today)
    if tonight:
        return tonight.number
    upcoming = [w for w in weeks if w.date is not None and w.date > today]
    if upcoming:
        return min(upcoming, key=lambda w: w.date).number
    if any(w.date is not None for w in weeks):
        return max(w.number for w in weeks)
    return min(w.number for w in weeks)


def read_state(event: Event, params: QueryDict, today: date) -> ScheduleState:
    weeks = list(event.weeks.all())
    tonight = tonight_week(weeks, today)
    if params.get("view") == "tonight":
        return ScheduleState(tonight.number if tonight else None, "", None, True)

    division, flight = read_filters(event, params)
    week = to_int(params.get("week"))
    if week in {w.number for w in weeks}:
        return ScheduleState(week, division, flight, False)
    if tonight and not division and flight is None:
        return ScheduleState(tonight.number, "", None, True)
    return ScheduleState(default_week(weeks, today), division, flight, False)


def week_pills(weeks: list[Week]) -> list[WeekPill]:
    return [
        WeekPill(
            w.number,
            f"Wk{w.number} · Cancelled" if not _live(w) else f"Wk{w.number}",
            not _live(w),
        )
        for w in weeks
    ]
