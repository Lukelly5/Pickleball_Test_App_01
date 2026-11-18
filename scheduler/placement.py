from collections.abc import Sequence
from itertools import zip_longest

from scheduler.pairings import Pairing
from scheduler.types import Match


def place_night(
    week: int,
    flights: Sequence[tuple[str, list[list[Pairing]]]],
    courts: int,
) -> list[Match]:
    """Place one night's games into rounds and courts.

    Rotations are placed in order, so a team's games stay spread across the
    night. Within a rotation the flights' games are interleaved, then sorted
    so teams that have been waiting longest go first.
    """
    matches: list[Match] = []
    last_round: dict[str, int] = {}
    busy: dict[int, set[str]] = {}
    courts_used: dict[int, set[int]] = {}

    rotation_count = max((len(rots) for _, rots in flights), default=0)
    for k in range(rotation_count):
        per_flight = [
            [(flight_id, pairing) for pairing in rots[k]] if k < len(rots) else []
            for flight_id, rots in flights
        ]
        games = [
            game
            for group in zip_longest(*per_flight)
            for game in group
            if game is not None
        ]
        games.sort(
            key=lambda g: max(
                last_round.get(g[1][0].id, 0), last_round.get(g[1][1].id, 0)
            )
        )
        for flight_id, (team_a, team_b) in games:
            players = {*team_a.players, *team_b.players}
            r = 1
            while (
                len(courts_used.get(r, ())) >= courts
                or busy.get(r, set()) & players
            ):
                r += 1
            taken = courts_used.setdefault(r, set())
            court_no = next(c for c in range(1, courts + 1) if c not in taken)
            taken.add(court_no)
            busy.setdefault(r, set()).update(players)
            last_round[team_a.id] = r
            last_round[team_b.id] = r
            matches.append(Match(flight_id, week, r, court_no, team_a, team_b))
    return matches
