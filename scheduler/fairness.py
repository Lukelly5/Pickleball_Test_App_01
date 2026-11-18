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
