"""Command-line runner: parses input, calls the scheduler, prints the result."""

import argparse
import json
import sys
from collections.abc import Sequence

from scheduler.fairness import FairnessReport, fairness_report
from scheduler.fit import check_fit, fit_message
from scheduler.generate import generate
from scheduler.pairings import round_robin_preset
from scheduler.types import Flight, Match, Schedule, ScheduleError, Team

GAP = "   "


def _parse_ints(text: str, what: str) -> list[int]:
    try:
        return [int(part) for part in text.split(",")]
    except ValueError:
        raise ScheduleError(
            f"{what} must be whole numbers separated by commas, not '{text}'."
        ) from None


def _build_flights(
    team_counts: Sequence[int], games_by_flight: Sequence[Sequence[int]]
) -> list[Flight]:
    flights = []
    for i, (count, games) in enumerate(zip(team_counts, games_by_flight), start=1):
        teams = tuple(
            Team(f"F{i}-T{j}", f"F{i}-T{j}", (f"F{i}-T{j}-A", f"F{i}-T{j}-B"))
            for j in range(1, count + 1)
        )
        flights.append(Flight(f"F{i}", f"Flight {i}", teams, tuple(games)))
    return flights


def _full_round_robin(n_teams: int) -> int:
    return n_teams - 1 if n_teams % 2 == 0 else n_teams


def _league_flights(args: argparse.Namespace) -> tuple[list[Flight], int]:
    if args.file:
        return _load_file(args.file)
    if args.teams is None or args.weeks is None or args.courts is None:
        raise ScheduleError("League needs --teams, --weeks and --courts (or --file).")
    if args.weeks < 1:
        raise ScheduleError("Weeks must be at least 1.")
    if (args.games_per_team is None) == (args.preset is None):
        raise ScheduleError("Give exactly one of --games-per-team or --preset.")
    counts = _parse_ints(args.teams, "--teams")
    if args.preset:
        times = 1 if args.preset == "once" else 2
        games = [round_robin_preset(n, args.weeks, times) for n in counts]
    else:
        per_week = _parse_ints(args.games_per_team, "--games-per-team")
        if len(per_week) == 1:
            per_week = per_week * args.weeks
        elif len(per_week) != args.weeks:
            raise ScheduleError(
                f"--games-per-team has {len(per_week)} numbers but there are "
                f"{args.weeks} weeks; give one number or one per week."
            )
        games = [per_week] * len(counts)
    return _build_flights(counts, games), args.courts


def _tournament_flights(args: argparse.Namespace) -> list[Flight]:
    counts = _parse_ints(args.teams, "--teams")
    if args.games_per_team is None:
        games = [[_full_round_robin(n)] for n in counts]
    else:
        games = [[args.games_per_team]] * len(counts)
    return _build_flights(counts, games)


def _load_file(path: str) -> tuple[list[Flight], int]:
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except OSError:
        raise ScheduleError(f"Could not read the file {path}.") from None
    except ValueError:
        raise ScheduleError(f"The file {path} is not valid JSON.") from None
    try:
        return _flights_from_json(data)
    except (KeyError, TypeError, AttributeError) as problem:
        raise ScheduleError(
            f"The file {path} is not in the expected shape: check {problem}."
        ) from None


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _flights_from_json(data: dict) -> tuple[list[Flight], int]:
    courts = data["courts"]
    if not _is_int(courts):
        raise TypeError("courts")
    flights = []
    for i, raw in enumerate(data["flights"], start=1):
        if not isinstance(raw["name"], str):
            raise TypeError("flight name")
        games = raw["games_per_team"]
        if not isinstance(games, list) or not all(_is_int(g) for g in games):
            raise TypeError("games_per_team")
        teams = []
        for j, raw_team in enumerate(raw["teams"], start=1):
            if not isinstance(raw_team["name"], str):
                raise TypeError("team name")
            players = raw_team["players"]
            if (
                not isinstance(players, list)
                or len(players) != 2
                or not all(isinstance(p, str) for p in players)
            ):
                raise TypeError("players (exactly 2 names per team)")
            teams.append(Team(f"F{i}-T{j}", raw_team["name"], (players[0], players[1])))
        flights.append(Flight(f"F{i}", raw["name"], tuple(teams), tuple(games)))
    return flights, courts


def _table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(row[c]) for row in rows) for c in range(len(rows[0]))]
    return [
        GAP.join(cell.ljust(widths[c]) for c, cell in enumerate(row)).rstrip()
        for row in rows
    ]


def _times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(n, f"{n} times")


def _span(low: int, high: int) -> str:
    return str(low) if low == high else f"{low}–{high}"


def _format_week(
    week: int,
    matches: Sequence[Match],
    flights: Sequence[Flight],
    report: FairnessReport,
    names: dict[str, str],
) -> list[str]:
    flight_names = {f.id: f.name for f in flights}
    prefix = len(flights) > 1

    def cell(m: Match) -> str:
        text = f"{names[m.team_a.id]} v {names[m.team_b.id]}"
        return f"{flight_names[m.flight_id]}: {text}" if prefix else text

    lines = [f"Week {week}"]
    if not matches:
        return lines + ["(no games)"]
    courts = max(m.court_no for m in matches)
    rounds = max(m.round_no for m in matches)
    grid = [[""] + [f"Court {c}" for c in range(1, courts + 1)]]
    for r in range(1, rounds + 1):
        row = [f"Round {r}"] + [""] * courts
        for m in matches:
            if m.round_no == r:
                row[m.court_no] = cell(m)
        grid.append(row)
    lines += _table(grid)
    per_team = " · ".join(
        f"{names[tid]} {n}" for tid, n in report.games_by_week[week].items()
    )
    sit = max(report.longest_sit[week].values(), default=0)
    unit = "round" if sit == 1 else "rounds"
    lines.append(f"Per team: {per_team} · longest sit {sit} {unit}")
    return lines


def _format_totals(
    schedule: Schedule, flights: Sequence[Flight], report: FairnessReport
) -> list[str]:
    lines = []
    for flight in flights:
        ids = {t.id for t in flight.teams}
        games = sum(1 for m in schedule.matches if m.flight_id == flight.id)
        per_team = [report.games_total[tid] for tid in ids]
        pairs = [n for pair, n in report.pair_counts.items() if pair <= ids]
        label = "Total" if len(flights) == 1 else f"Total ({flight.name})"
        if min(pairs) == max(pairs):
            meets = _times(pairs[0])
        else:
            meets = f"{min(pairs)}–{max(pairs)} times"
        lines.append(
            f"{label}: {games} games · {_span(min(per_team), max(per_team))} per team"
            f" · every pair meets {meets}"
        )
    return lines


def _render(schedule: Schedule, flights: Sequence[Flight]) -> list[str]:
    report = fairness_report(schedule, flights)
    names = {t.id: t.name for f in flights for t in f.teams}
    lines: list[str] = []
    for week in sorted(report.games_by_week):
        lines += _format_week(week, schedule.week(week), flights, report, names)
        lines.append("")
    return lines + _format_totals(schedule, flights, report)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scheduler")
    sub = parser.add_subparsers(dest="command", required=True)

    league = sub.add_parser("league", help="multi-week league schedule")
    league.add_argument("--teams", help="teams per flight, comma-separated, e.g. 4 or 4,6")
    league.add_argument("--weeks", type=int)
    league.add_argument("--games-per-team", help="one number, or one per week, e.g. 1,2")
    league.add_argument("--preset", choices=["once", "twice"], help="round robin once or twice")
    league.add_argument("--courts", type=int)
    league.add_argument("--file", help="JSON file describing courts, flights and teams")

    tournament = sub.add_parser("tournament", help="one-day tournament with a fit check")
    tournament.add_argument("--teams", required=True)
    tournament.add_argument("--courts", type=int, required=True)
    tournament.add_argument("--game-minutes", type=int, required=True)
    tournament.add_argument("--window", type=int, required=True, help="minutes available")
    tournament.add_argument("--games-per-team", type=int, help="default: full round robin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "league":
            flights, courts = _league_flights(args)
            lines = _render(generate(flights, courts), flights)
        else:
            flights, courts = _tournament_flights(args), args.courts
            lines = _render(generate(flights, courts), flights)
            fit = check_fit(flights, courts, args.game_minutes, args.window)
            lines += ["", fit_message(fit)]
    except ScheduleError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0
