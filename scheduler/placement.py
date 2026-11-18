"""Pass 2: arrange one night's games into rounds and courts.

Which games are played is decided before this (Pass 1). Here they are only
arranged, in three steps:

1. Two first drafts are made (`_draft_by_rotation`, `_draft_longest_wait_first`).
2. Each draft is tidied up: games are moved between rounds for as long as
   that shortens the waits between a team's games (`_Night.close_gaps`).
3. The tidied draft with the shorter waits is kept.

No step lets a player be in two games in one round, uses more courts than
there are, or adds a round to the first draft.
"""

from collections.abc import Sequence
from itertools import zip_longest

from scheduler.pairings import Pairing
from scheduler.types import Match

Game = tuple[str, Pairing]  # (flight id, the two teams)


def place_night(
    week: int,
    flights: Sequence[tuple[str, list[list[Pairing]]]],
    courts: int,
) -> list[Match]:
    """Place one night's games into rounds and courts."""
    games, rounds = _draft_by_rotation(flights, courts)
    night = _Night(games, courts)
    rounds = night.close_gaps(rounds)
    if night.cost(rounds) > 0:
        other = _draft_longest_wait_first(games, courts, max(rounds))
        if other is not None:
            other = night.close_gaps(other)
            if night.cost(other) < night.cost(rounds):
                rounds = other

    next_court: dict[int, int] = {}
    matches: list[Match] = []
    for (flight_id, (team_a, team_b)), r in zip(games, rounds):
        court_no = next_court.get(r, 1)
        next_court[r] = court_no + 1
        matches.append(Match(flight_id, week, r, court_no, team_a, team_b))
    return matches


def _players(game: Game) -> set[str]:
    team_a, team_b = game[1]
    return {*team_a.players, *team_b.players}


def _draft_by_rotation(
    flights: Sequence[tuple[str, list[list[Pairing]]]], courts: int
) -> tuple[list[Game], list[int]]:
    """First draft: one rotation at a time, each game in the earliest round
    with a free court and none of its players playing.

    Within a rotation the flights' games are interleaved, then sorted so
    teams that have been waiting longest go first. Returns the games in the
    order they were placed and the round given to each.
    """
    games: list[Game] = []
    rounds: list[int] = []
    last_round: dict[str, int] = {}
    busy: dict[int, set[str]] = {}
    used: dict[int, int] = {}

    rotation_count = max((len(rots) for _, rots in flights), default=0)
    for k in range(rotation_count):
        per_flight = [
            [(flight_id, pairing) for pairing in rots[k]] if k < len(rots) else []
            for flight_id, rots in flights
        ]
        rotation = [
            game
            for group in zip_longest(*per_flight)
            for game in group
            if game is not None
        ]
        rotation.sort(
            key=lambda g: max(
                last_round.get(g[1][0].id, 0), last_round.get(g[1][1].id, 0)
            )
        )
        for game in rotation:
            players = _players(game)
            r = 1
            while used.get(r, 0) >= courts or busy.get(r, set()) & players:
                r += 1
            used[r] = used.get(r, 0) + 1
            busy.setdefault(r, set()).update(players)
            for team in game[1]:
                last_round[team.id] = r
            games.append(game)
            rounds.append(r)
    return games, rounds


def _draft_longest_wait_first(
    games: Sequence[Game], courts: int, round_limit: int
) -> list[int] | None:
    """Second draft: fill one round at a time. For each free court take the
    game whose team has waited longest since its last game; a team that has
    not played yet is in no hurry.

    A team that has as many games left as there are rounds left must play
    now, so its game jumps the queue. Ties go to the team with more games
    left, then to list order. Returns None if the night would need more
    than `round_limit` rounds.
    """
    games_left: dict[str, int] = {}
    for _, pairing in games:
        for team in pairing:
            games_left[team.id] = games_left.get(team.id, 0) + 1

    rounds = [0] * len(games)
    waiting = list(range(len(games)))
    last_round: dict[str, int] = {}
    for round_no in range(1, round_limit + 1):
        rounds_left = round_limit - round_no + 1
        busy: set[str] = set()
        for _ in range(courts):
            best: int | None = None
            best_key: tuple[bool, int, int] | None = None
            for i in waiting:
                if busy & _players(games[i]):
                    continue
                teams = games[i][1]
                most_left = max(games_left[t.id] for t in teams)
                key = (
                    most_left >= rounds_left,
                    max(round_no - last_round.get(t.id, round_no) for t in teams),
                    most_left,
                )
                if best_key is None or key > best_key:
                    best, best_key = i, key
            if best is None:
                break
            waiting.remove(best)
            rounds[best] = round_no
            busy.update(_players(games[best]))
            for team in games[best][1]:
                last_round[team.id] = round_no
                games_left[team.id] -= 1
        if not waiting:
            return rounds
    return None


class _Night:
    """The night's games plus what is needed to judge and tidy an
    arrangement. An arrangement is a list: the round of each game."""

    def __init__(self, games: Sequence[Game], courts: int) -> None:
        self.courts = courts
        self.players = [_players(game) for game in games]
        self.teams = [(a.id, b.id) for _, (a, b) in games]
        self.games_of: dict[str, list[int]] = {}
        for i, pair in enumerate(self.teams):
            for team_id in pair:
                self.games_of.setdefault(team_id, []).append(i)
        # A sit of s idle rounds costs weight ** s. The weight is bigger than
        # the number of sits in the night, so one longer sit always costs
        # more than any number of shorter ones: the longest sit is shortened
        # first, then the next longest, and so on.
        self.weight = 2 * len(games) + 1

    def _team_cost(
        self, team_id: str, rounds: Sequence[int], moved: dict[int, int]
    ) -> int:
        played = sorted(moved.get(g, rounds[g]) for g in self.games_of[team_id])
        return sum(
            self.weight ** (b - a - 1) for a, b in zip(played, played[1:]) if b - a > 1
        )

    def cost(self, rounds: Sequence[int]) -> int:
        """How bad the waits are; 0 means nobody sits between games."""
        return sum(self._team_cost(team_id, rounds, {}) for team_id in self.games_of)

    def close_gaps(self, rounds: Sequence[int]) -> list[int]:
        """Tidy up: make the single change that shortens the waits most, and
        repeat until no change helps. Never adds a round.

        A change moves one game to a round with a free court, or trades the
        rounds of two games; it is only tried if no player would end up in
        two games in one round. When no such change helps, trading two whole
        rounds is tried instead. Ties go to the change found first.
        """
        rounds = list(rounds)
        games = range(len(rounds))
        now = {t: self._team_cost(t, rounds, {}) for t in self.games_of}

        def gain(moved: dict[int, int]) -> int:
            """How much the waits shrink if these games change round."""
            affected = sorted({t for g in moved for t in self.teams[g]})
            return sum(now[t] - self._team_cost(t, rounds, moved) for t in affected)

        # alone[i][r] is the gain from moving only game i to round r. It is
        # worked out once and redone only for teams whose games just moved.
        alone: dict[int, dict[int, int]] = {}
        # Each change lowers the cost, so this ends by itself; the cap is a backstop.
        for _ in range(10 * len(rounds)):
            in_round: dict[int, list[int]] = {}
            for i, r in enumerate(rounds):
                in_round.setdefault(r, []).append(i)
            used = sorted(in_round)
            for i in games:
                if i not in alone:
                    alone[i] = {r: gain({i: r}) for r in used}
            # clash[i][r]: the games in round r that share a player with game i.
            clash = [
                {
                    r: [g for g in in_round[r] if g != i and self.players[g] & self.players[i]]
                    for r in used
                }
                for i in games
            ]

            best: dict[int, int] = {}
            best_gain = 0
            for i in games:
                home = rounds[i]
                for r in used:
                    if r == home or clash[i][r] or len(in_round[r]) >= self.courts:
                        continue
                    if alone[i][r] > best_gain:
                        best, best_gain = {i: r}, alone[i][r]
                for j in range(i + 1, len(rounds)):
                    away = rounds[j]
                    if away == home or clash[i][away] not in ([], [j]):
                        continue
                    if clash[j][home] not in ([], [i]):
                        continue
                    if set(self.teams[i]) & set(self.teams[j]):
                        value = gain({i: away, j: home})
                    else:
                        value = alone[i][away] + alone[j][home]
                    if value > best_gain:
                        best, best_gain = {i: away, j: home}, value
            if not best:
                for n, a in enumerate(used):
                    for b in used[n + 1:]:
                        moved = {g: b for g in in_round[a]} | {g: a for g in in_round[b]}
                        if (value := gain(moved)) > best_gain:
                            best, best_gain = moved, value
            if not best:
                break
            for game, r in best.items():
                rounds[game] = r
            for team_id in sorted({t for g in best for t in self.teams[g]}):
                now[team_id] = self._team_cost(team_id, rounds, {})
                for game in self.games_of[team_id]:
                    alone.pop(game, None)
        # Close up any round that was emptied.
        number = {r: n for n, r in enumerate(sorted(set(rounds)), start=1)}
        return [number[r] for r in rounds]
