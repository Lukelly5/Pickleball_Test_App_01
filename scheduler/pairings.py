from collections.abc import Sequence

from scheduler.types import Flight, ScheduleError, Team

Pairing = tuple[Team, Team]


def rotations(teams: Sequence[Team]) -> list[list[Pairing]]:
    """Circle-method round robin: one list of pairings per rotation.

    With an odd number of teams a bye seat is added, so each team sits out
    exactly one rotation per cycle.
    """
    seats: list[Team | None] = list(teams) + ([None] if len(teams) % 2 else [])
    n = len(seats)
    result: list[list[Pairing]] = []
    for _ in range(n - 1):
        rotation: list[Pairing] = []
        for i in range(n // 2):
            a, b = seats[i], seats[n - 1 - i]
            if a is not None and b is not None:
                rotation.append((a, b))
        result.append(rotation)
        seats = [seats[0], seats[-1], *seats[1:-1]]
    return result


def weekly_rotations(flight: Flight) -> list[list[list[Pairing]]]:
    """Slice the rotation cycle into weeks; index [week-1][k] is the k-th
    rotation played that week. A rotation is never split across weeks, and
    a week with zero games does not advance the cycle."""
    cycle = rotations(flight.teams)
    position = 0
    weeks: list[list[list[Pairing]]] = []
    for games in flight.games_per_team_by_week:
        week = [cycle[(position + k) % len(cycle)] for k in range(games)]
        position += games
        weeks.append(week)
    return weeks


def round_robin_preset(n_teams: int, weeks: int, times: int) -> tuple[int, ...]:
    """Games per team per week for playing everyone `times` times."""
    total = times * (n_teams - 1 if n_teams % 2 == 0 else n_teams)
    if total < weeks:
        label = "once" if times == 1 else "twice"
        alternative = "twice" if times == 1 else "custom"
        raise ScheduleError(
            f"Round robin {label} is {total} games per team, but you have "
            f"{weeks} weeks. Week {total + 1} has no games — reduce weeks "
            f"or choose {alternative}."
        )
    base, extra = divmod(total, weeks)
    return tuple(base + 1 if w < extra else base for w in range(weeks))
