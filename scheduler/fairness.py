from collections.abc import Sequence
from dataclasses import dataclass

from scheduler.types import Flight, Schedule


@dataclass(frozen=True)
class FairnessReport:
    games_by_week: dict[int, dict[str, int]]
    games_total: dict[str, int]
    pair_counts: dict[frozenset[str], int]
    longest_sit: dict[int, dict[str, int]]


def fairness_report(schedule: Schedule, flights: Sequence[Flight]) -> FairnessReport:
    team_ids = [t.id for f in flights for t in f.teams]
    weeks = range(
        1,
        max(
            [len(f.games_per_team_by_week) for f in flights]
            + [m.week for m in schedule.matches]
            + [0]
        )
        + 1,
    )

    games_by_week = {w: {tid: 0 for tid in team_ids} for w in weeks}
    rounds_by_week: dict[int, dict[str, list[int]]] = {
        w: {tid: [] for tid in team_ids} for w in weeks
    }
    pair_counts: dict[frozenset[str], int] = {}
    for f in flights:
        for i, a in enumerate(f.teams):
            for b in f.teams[i + 1:]:
                pair_counts[frozenset((a.id, b.id))] = 0

    for m in schedule.matches:
        for tid in (m.team_a.id, m.team_b.id):
            games_by_week[m.week][tid] += 1
            rounds_by_week[m.week][tid].append(m.round_no)
        pair_counts[frozenset((m.team_a.id, m.team_b.id))] += 1

    games_total = {
        tid: sum(games_by_week[w][tid] for w in weeks) for tid in team_ids
    }
    longest_sit = {
        w: {
            tid: max(
                (b - a - 1 for a, b in zip(sorted(r), sorted(r)[1:])), default=0
            )
            for tid, r in rounds_by_week[w].items()
        }
        for w in weeks
    }
    return FairnessReport(games_by_week, games_total, pair_counts, longest_sit)


def pair_meet_text(counts: list[int]) -> str:
    """How often pairs meet, e.g. "once", "twice", "3 times" or "2–3 times"."""
    if min(counts) != max(counts):
        return f"{min(counts)}–{max(counts)} times"
    return {1: "once", 2: "twice"}.get(counts[0], f"{counts[0]} times")


def summary_line(report: FairnessReport, flight: Flight) -> str:
    """One flight's totals in words, e.g.
    "16 games · 8 per team · every pair meets 2–3 times"."""
    ids = [t.id for t in flight.teams]
    per_team = [report.games_total[tid] for tid in ids]
    games = sum(per_team) // 2
    pairs = [
        report.pair_counts[frozenset((a, b))]
        for i, a in enumerate(ids)
        for b in ids[i + 1:]
    ]
    low, high = min(per_team), max(per_team)
    each = str(low) if low == high else f"{low}–{high}"
    return (
        f"{games} {'game' if games == 1 else 'games'} · {each} per team"
        f" · every pair meets {pair_meet_text(pairs)}"
    )
