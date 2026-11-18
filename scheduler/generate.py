from collections.abc import Sequence

from scheduler.pairings import weekly_rotations
from scheduler.placement import place_night
from scheduler.types import Flight, Match, Schedule, ScheduleError


def _validate(flights: Sequence[Flight], courts: int) -> None:
    if courts < 1:
        raise ScheduleError("Courts must be at least 1.")
    flight_ids: set[str] = set()
    team_ids: set[str] = set()
    for flight in flights:
        if len(flight.teams) < 2:
            raise ScheduleError(
                f"Add at least 2 teams to {flight.name} before generating."
            )
        if flight.id in flight_ids:
            raise ScheduleError(f"Flight id {flight.id} is used more than once.")
        flight_ids.add(flight.id)
        if any(g < 0 for g in flight.games_per_team_by_week):
            raise ScheduleError(
                f"{flight.name} has a negative number of games in a week."
            )
        seen_players: set[str] = set()
        for team in flight.teams:
            if team.id in team_ids:
                raise ScheduleError(f"Team id {team.id} is used more than once.")
            team_ids.add(team.id)
            if len(set(team.players)) != len(team.players):
                raise ScheduleError(
                    f"{team.players[0]} is listed twice on {team.name}."
                )
            for player in team.players:
                if player in seen_players:
                    raise ScheduleError(
                        f"{player} is on two teams in {flight.name}."
                    )
                seen_players.add(player)
    if len({len(f.games_per_team_by_week) for f in flights}) > 1:
        raise ScheduleError("All flights must have the same number of weeks.")


def generate(flights: Sequence[Flight], courts: int) -> Schedule:
    _validate(flights, courts)
    per_flight = [weekly_rotations(f) for f in flights]
    matches: list[Match] = []
    for week in range(len(per_flight[0]) if per_flight else 0):
        night = [(f.id, per_flight[i][week]) for i, f in enumerate(flights)]
        matches.extend(place_night(week + 1, night, courts))
    return Schedule(tuple(matches), courts)
