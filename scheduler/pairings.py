from collections.abc import Sequence

from scheduler.types import Team

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
