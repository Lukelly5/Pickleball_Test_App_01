"""Page data for the schedule preview: the week grid, click rules, fairness lines.

Plain data, no HTTP. The views render it and the templates read `tile.actions`
without any logic of their own.
"""

import re
from dataclasses import dataclass

from django.http import QueryDict

from league.models import Division, Event, Flight, Match, Team, Week
from league.schedule_edits import scored_match_ids
from league.scheduling import event_flights, load_schedule
from scheduler import fairness_report, pair_meet_text

PICK_RE = re.compile(r"^(g\d+|t\d+[ab])$")
LEVEL_LABELS = dict(Division.Level.choices)


@dataclass(frozen=True)
class TeamSlot:
    key: str  # "t<match_id>a" / "t<match_id>b"
    name: str
    level: str
    withdrawn: bool


@dataclass(frozen=True)
class Tile:
    key: str  # "g<match_id>" | "o<round>-<court>" | "x<match_id>" (cancelled/void)
    kind: str  # "game" | "open" | "cancelled"
    round_no: int
    court_no: int
    match_id: int | None
    flight_name: str
    level: str  # "" for open tiles
    teams: tuple[TeamSlot, ...]  # () for open tiles
    locked: bool  # scored, withdrawn team, or cancelled week: not clickable
    faded: bool  # outside the filter: not clickable
    actions: dict[str, tuple[str, str | None]]  # click key -> resolve_click result


@dataclass(frozen=True)
class WeekTab:
    number: int
    label: str
    cancelled: bool


@dataclass(frozen=True)
class Board:
    event: Event
    week: int
    tabs: list[WeekTab]
    courts: int
    rows: list[list[Tile]]  # rows[i] is Round i+1, one Tile per court 1..courts
    read_only: bool  # the week is cancelled
    division: str
    flight: int | None
    pick: str | None
    divisions: list[tuple[str, str]]  # (level, label) the event has
    flights: list[tuple[int, str]]  # (pk, name), narrowed to the chosen division


@dataclass(frozen=True)
class FairLine:
    label: str
    text: str
    ok: bool
    chip: str = ""


@dataclass(frozen=True)
class FlightFairness:
    flight_name: str
    lines: list[FairLine]


# --- state ---------------------------------------------------------------


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_state(event: Event, params: QueryDict) -> dict:
    """The page state from the query string; junk values fall back to defaults."""
    week_numbers = list(event.weeks.values_list("number", flat=True))
    week = _int(params.get("week"))
    if week not in week_numbers:
        week = 1

    levels = set(Division.objects.filter(event=event).values_list("level", flat=True))
    division = params.get("division", "")
    if division not in levels:
        division = ""

    flights = Flight.objects.filter(division__event=event)
    if division:
        flights = flights.filter(division__level=division)
    flight = _int(params.get("flight"))
    if flight not in set(flights.values_list("pk", flat=True)):
        flight = None

    pick = params.get("pick", "")
    if PICK_RE.match(pick):
        match_id = int(pick[1:].rstrip("ab"))
        on_week = Match.objects.filter(
            pk=match_id, flight__division__event=event, week__number=week
        ).exists()
        if not on_week:
            pick = ""
    else:
        pick = ""
    return {"week": week, "division": division, "flight": flight, "pick": pick or None}


# --- click rules ---------------------------------------------------------


def _tile_keys(tile: Tile, read_only: bool) -> tuple[str, ...]:
    """The keys a tile answers to, or () when it can't be clicked."""
    if read_only or tile.locked or tile.faded:
        return ()
    if tile.kind == "game":
        return (tile.key, *(s.key for s in tile.teams))
    if tile.kind == "open":
        return (tile.key,)
    return ()


def _decide(pick: str | None, target: str) -> tuple[str, str | None]:
    """The pick-then-act table for a target already known to be clickable."""
    if target[0] == "o":
        return ("move", target) if pick and pick[0] == "g" else ("select", None)
    if pick is None:
        return ("select", target)
    match_id = target[1:].rstrip("ab")
    if pick[0] == "g":
        if match_id == pick[1:]:
            return ("select", None)
        return ("swap_games", f"g{match_id}")
    if target[0] == "t":
        return ("select", None) if target == pick else ("swap_teams", target)
    return ("select", target)


def resolve_click(board: Board, target: str) -> tuple[str, str | None]:
    """What clicking `target` does: ("select", new_pick_or_None) or
    ("swap_games" | "swap_teams" | "move", target_key). Anything that is not a
    clickable key on this board only clears the pick."""
    keys = {k for row in board.rows for t in row for k in _tile_keys(t, board.read_only)}
    if target not in keys:
        return ("select", None)
    return _decide(board.pick, target)


# --- board ---------------------------------------------------------------


def _slot(match: Match, side: str, level: str) -> TeamSlot:
    team = match.team_a if side == "a" else match.team_b
    return TeamSlot(f"t{match.pk}{side}", team.name, level, team.withdrawn_at is not None)


def build_board(event: Event, state: dict) -> Board:
    week_no, division, flight_id = state["week"], state["division"], state["flight"]
    weeks = list(event.weeks.all())
    tabs = [
        WeekTab(
            w.number,
            f"Week {w.number} · Cancelled"
            if w.status == Week.Status.CANCELLED
            else f"Week {w.number}",
            w.status == Week.Status.CANCELLED,
        )
        for w in weeks
    ]
    read_only = any(t.cancelled for t in tabs if t.number == week_no)

    divisions = [
        (d.level, LEVEL_LABELS[d.level]) for d in Division.objects.filter(event=event).order_by("pk")
    ]
    flight_rows = Flight.objects.filter(division__event=event).select_related("division")
    if division:
        flight_rows = flight_rows.filter(division__level=division)
    flight_rows = flight_rows.order_by("division__pk", "pk")
    flights = [(f.pk, f.name) for f in flight_rows]
    shown = {flight_id} if flight_id else {pk for pk, _ in flights}
    filtered = bool(division or flight_id)

    matches = list(
        Match.objects.filter(flight__division__event=event, week__number=week_no)
        .select_related("flight__division", "team_a", "team_b")
        .order_by("round_no", "court_no")
    )
    scored = scored_match_ids(event)
    by_slot = {(m.round_no, m.court_no): m for m in matches}
    top_round = max((m.round_no for m in matches), default=0)

    grid: list[list[Tile]] = []
    for rnd in range(1, top_round + 1):
        row = []
        for court in range(1, event.courts + 1):
            m = by_slot.get((rnd, court))
            if m is None:
                row.append(Tile(f"o{rnd}-{court}", "open", rnd, court, None, "", "", (), False, False, {}))
                continue
            level = m.flight.division.level
            faded = filtered and m.flight_id not in shown
            if m.status in (Match.Status.CANCELLED, Match.Status.VOID):
                kind, key, locked = "cancelled", f"x{m.pk}", True
            else:
                kind, key = "game", f"g{m.pk}"
                locked = (
                    m.pk in scored
                    or m.team_a.withdrawn_at is not None
                    or m.team_b.withdrawn_at is not None
                    or read_only
                )
            row.append(
                Tile(
                    key, kind, rnd, court, m.pk, m.flight.name, level,
                    (_slot(m, "a", level), _slot(m, "b", level)), locked, faded, {},
                )
            )
        grid.append(row)

    clickable = {k for row in grid for t in row for k in _tile_keys(t, read_only)}
    pick = state["pick"] if state["pick"] in clickable else None
    rows = [
        [
            Tile(
                t.key, t.kind, t.round_no, t.court_no, t.match_id, t.flight_name, t.level,
                t.teams, t.locked, t.faded,
                {k: _decide(pick, k) for k in _tile_keys(t, read_only)},
            )
            for t in row
        ]
        for row in grid
    ]
    return Board(
        event, week_no, tabs, event.courts, rows, read_only, division, flight_id, pick,
        divisions, flights,
    )


# --- fairness ------------------------------------------------------------


def _rounds(n: int) -> str:
    return f"{n} round" if n == 1 else f"{n} rounds"


def _each(low: int, high: int) -> str:
    return f"{low} each" if low == high else f"{low}–{high} each"


def fairness(event: Event, week: int, flight_ids: set[int] | None) -> list[FlightFairness]:
    """One block per flight: even-handedness of games, pairings and sits."""
    schedule, flights = load_schedule(event)
    report = fairness_report(schedule, flights)
    withdrawn = {
        str(pk)
        for pk in Team.objects.filter(
            flight__division__event=event, withdrawn_at__isnull=False
        ).values_list("pk", flat=True)
    }
    result = []
    for flight in flights:
        if flight_ids is not None and int(flight.id) not in flight_ids:
            continue
        teams = [t for t in flight.teams if t.id not in withdrawn]
        if not teams:
            continue
        ids = [t.id for t in teams]
        name = {t.id: t.name for t in teams}
        plan = flight.games_per_team_by_week
        planned = plan[week - 1] if 0 <= week - 1 < len(plan) else 0
        this_week = {tid: report.games_by_week.get(week, {}).get(tid, 0) for tid in ids}
        allowed = {planned, planned - 1} if len(teams) % 2 else {planned}
        off = [tid for tid in ids if this_week[tid] not in allowed]
        if off:
            games = FairLine("Games this week", ", ".join(f"{name[t]} {this_week[t]}" for t in off), False)
        else:
            games = FairLine(
                "Games this week", _each(min(this_week.values()), max(this_week.values())), True
            )

        totals = {tid: report.games_total[tid] for tid in ids}
        low, high = min(totals.values()), max(totals.values())
        if high - low <= 1:
            season = FairLine("Season total", _each(low, high), True)
        else:
            lo_t = next(t for t in ids if totals[t] == low)
            hi_t = next(t for t in ids if totals[t] == high)
            season = FairLine(
                "Season total", f"{low}–{high} per team", False,
                f"{name[lo_t]} {low} · {name[hi_t]} {high}",
            )

        counts = [
            report.pair_counts[frozenset((a, b))]
            for i, a in enumerate(ids)
            for b in ids[i + 1:]
        ]
        if counts:
            pairs = FairLine("Pairs meeting", pair_meet_text(counts), max(counts) - min(counts) <= 1)
        else:
            pairs = FairLine("Pairs meeting", "none", True)

        sits = {tid: report.longest_sit.get(week, {}).get(tid, 0) for tid in ids}
        worst = max(sits.values())
        text = "none" if worst == 0 else _rounds(worst)
        if worst <= 1:
            sit = FairLine("Longest sit", text, True)
        else:
            who = next(t for t in ids if sits[t] == worst)
            sit = FairLine("Longest sit", text, False, f"{name[who]} · {_rounds(worst)}")
        result.append(FlightFairness(flight.name, [games, season, pairs, sit]))
    return result

