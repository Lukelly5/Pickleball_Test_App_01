from dataclasses import dataclass


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Team:
    id: str
    name: str
    players: tuple[str, ...]  # 2 names, or none when the team's players aren't named


@dataclass(frozen=True)
class Flight:
    id: str
    name: str
    teams: tuple[Team, ...]
    games_per_team_by_week: tuple[int, ...]


@dataclass(frozen=True)
class Match:
    flight_id: str
    week: int
    round_no: int
    court_no: int
    team_a: Team
    team_b: Team


@dataclass(frozen=True)
class Schedule:
    matches: tuple[Match, ...]
    courts: int

    def __post_init__(self) -> None:
        ordered = tuple(
            sorted(self.matches, key=lambda m: (m.week, m.round_no, m.court_no))
        )
        object.__setattr__(self, "matches", ordered)

    def week(self, n: int) -> tuple[Match, ...]:
        return tuple(m for m in self.matches if m.week == n)
