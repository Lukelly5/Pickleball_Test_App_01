"""State for the read-only Schedule tab: which week, filters, and Tonight mode."""

from dataclasses import dataclass
from datetime import date

from django.http import QueryDict

from league.filters import filter_options, read_filters, to_int
from league.models import Event, Match, Team, Week


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


@dataclass(frozen=True)
class Chip:
    points: int
    won: bool


@dataclass(frozen=True)
class Side:
    team_id: int
    name: str
    level: str
    withdrawn: bool
    mine: bool
    winner: bool
    chips: tuple[Chip, ...]


@dataclass(frozen=True)
class Card:
    match_id: int
    round_no: int
    court_no: int
    flight_name: str
    level: str
    sides: tuple[Side, Side]
    status: str  # Match.Status value
    forfeit: bool
    winner_name: str  # "" when no winner

    @property
    def faded(self) -> bool:
        return self.status in _NOT_PLAYED


@dataclass(frozen=True)
class Round:
    number: int
    cards: list[Card]
    sitting_out: list[str]


@dataclass(frozen=True)
class SchedulePage:
    event: Event
    state: ScheduleState
    pills: list[WeekPill]
    week_date: date | None
    cancelled: bool
    divisions: list[tuple[str, str]]
    flights: list[tuple[int, str]]
    rounds: list[Round]
    has_matches: bool
    heading: str  # "Tonight — Week 2 · all flights" in Tonight mode with a game, else ""
    next_night: Week | None  # only in Tonight mode with no game today
    empty_message: str  # "" when rounds exist


_NOT_PLAYED = (Match.Status.CANCELLED, Match.Status.VOID)


def _card(match: Match, my_team_ids: frozenset[int]) -> Card:
    forfeit = match.forfeited_by_id is not None
    level = match.flight.division.level
    games = sorted(match.games.all(), key=lambda g: g.game_no)

    def side(team: Team, mine_side: bool) -> Side:
        chips = ()
        if not forfeit:
            chips = tuple(
                Chip(
                    g.points_a if mine_side else g.points_b,
                    (g.points_a > g.points_b) if mine_side else (g.points_b > g.points_a),
                )
                for g in games
            )
        return Side(
            team.pk,
            team.name,
            level,
            team.withdrawn_at is not None,
            team.pk in my_team_ids,
            team.pk == match.winner_id,
            chips,
        )

    return Card(
        match.pk,
        match.round_no,
        match.court_no,
        match.flight.name,
        level,
        (side(match.team_a, True), side(match.team_b, False)),
        match.status,
        forfeit,
        match.winner.name if match.winner else "",
    )


def _rounds(
    event: Event, week: Week, state: ScheduleState, my_team_ids: frozenset[int]
) -> list[Round]:
    matches = Match.objects.filter(week=week, flight__division__event=event)
    if state.flight:
        matches = matches.filter(flight_id=state.flight)
    elif state.division:
        matches = matches.filter(flight__division__level=state.division)
    matches = list(
        matches.select_related("flight__division", "team_a", "team_b", "winner")
        .prefetch_related("games")
        .order_by("round_no", "court_no")
    )
    flight_teams = []
    if state.flight:
        flight_teams = list(Team.objects.filter(flight_id=state.flight, withdrawn_at__isnull=True))

    rounds = []
    for number in sorted({m.round_no for m in matches}):
        in_round = [m for m in matches if m.round_no == number]
        playing = {
            t.pk
            for m in in_round
            if m.status not in _NOT_PLAYED
            for t in (m.team_a, m.team_b)
        }
        rounds.append(
            Round(
                number,
                [_card(m, my_team_ids) for m in in_round],
                sorted(t.name for t in flight_teams if t.pk not in playing),
            )
        )
    return rounds


def build_page(
    event: Event,
    state: ScheduleState,
    today: date,
    my_team_ids: frozenset[int] = frozenset(),
) -> SchedulePage:
    weeks = list(event.weeks.all())
    week = next((w for w in weeks if w.number == state.week), None)
    cancelled = week is not None and not _live(week)
    divisions, flights = filter_options(event, state.division)
    has_matches = Match.objects.filter(flight__division__event=event).exists()
    rounds = _rounds(event, week, state, my_team_ids) if week and not cancelled else []

    if not has_matches:
        empty = "The schedule hasn't been published yet."
    elif cancelled:
        empty = "No games this week (cancelled)."
    elif rounds:
        empty = ""
    elif state.tonight:
        empty = "No games tonight."
    elif state.division or state.flight:
        empty = "No games for this flight this week."
    else:
        empty = "No games this week."

    return SchedulePage(
        event=event,
        state=state,
        pills=week_pills(weeks),
        week_date=week.date if week else None,
        cancelled=cancelled,
        divisions=divisions,
        flights=flights,
        rounds=rounds,
        has_matches=has_matches,
        heading=f"Tonight — Week {week.number} · all flights" if state.tonight and week else "",
        next_night=next_game_night(weeks, today) if state.tonight and week is None else None,
        empty_message=empty,
    )
