from collections.abc import Sequence

from scheduler.types import Flight, Team


def make_teams(n: int, prefix: str = "T") -> tuple[Team, ...]:
    return tuple(
        Team(
            id=f"{prefix}{i}",
            name=f"Team {prefix}{i}",
            players=(f"{prefix}{i}-a", f"{prefix}{i}-b"),
        )
        for i in range(1, n + 1)
    )


def make_flight(
    n: int, games: Sequence[int], id: str = "F1", prefix: str = "T"
) -> Flight:
    return Flight(
        id=id,
        name=f"Flight {id}",
        teams=make_teams(n, prefix),
        games_per_team_by_week=tuple(games),
    )
