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

from bisect import bisect_right, insort
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
        self.teams = [(a.id, b.id) for _, (a, b) in games]
        self.games_of: dict[str, list[int]] = {}
        for i, pair in enumerate(self.teams):
            for team_id in pair:
                self.games_of.setdefault(team_id, []).append(i)
        # rivals[i]: the other games that share a player with game i, so
        # can never be in the same round as it.
        games_with: dict[str, list[int]] = {}
        for i, game in enumerate(games):
            for player in sorted(_players(game)):
                games_with.setdefault(player, []).append(i)
        self.rivals: list[set[int]] = [
            {g for player in _players(game) for g in games_with[player]} - {i}
            for i, game in enumerate(games)
        ]
        # A sit of s idle rounds costs weight ** s. The weight is bigger than
        # the number of sits in the night, so one longer sit always costs
        # more than any number of shorter ones: the longest sit is shortened
        # first, then the next longest, and so on.
        self.weight = 2 * len(games) + 1

    def cost(self, rounds: Sequence[int]) -> int:
        """How bad the waits are; 0 means nobody sits between games."""
        total = 0
        for games in self.games_of.values():
            played = sorted(rounds[g] for g in games)
            total += sum(
                self.weight ** (b - a - 1)
                for a, b in zip(played, played[1:])
                if b - a > 1
            )
        return total

    def close_gaps(self, rounds: Sequence[int]) -> list[int]:
        """Tidy up: make the single change that shortens the waits most, and
        repeat until no change helps. Never adds a round.

        A change moves one game to a round with a free court, or trades the
        rounds of two games; it is only tried if no player would end up in
        two games in one round. When no such change helps, trading two whole
        rounds is tried instead. Ties go to the change found first: lowest
        game, a move before a trade, lowest round or partner.

        The answer is the same as looking at every change afresh each time.
        To save work, the bookkeeping below is kept up to date as games
        move, and a game's best change is only worked out again when the
        last change could have altered it.
        """
        rounds = list(rounds)
        count = len(rounds)
        last = max(rounds, default=0)
        courts = self.courts
        teams = self.teams
        rivals = self.rivals

        # apart[d]: cost of two games of one team that are d rounds apart.
        apart = [0, 0] + [self.weight**s for s in range(1, last)]
        # members[r]: the games in round r.
        members: list[list[int]] = [[] for _ in range(last + 1)]
        for i, r in enumerate(rounds):
            members[r].append(i)
        # played[team]: the rounds the team plays in, in order.
        played = {t: sorted(rounds[g] for g in gs) for t, gs in self.games_of.items()}
        # blocked[i][r]: how many games in round r share a player with game i.
        blocked = [[0] * (last + 1) for _ in range(count)]
        for i in range(count):
            for k in rivals[i]:
                blocked[i][rounds[k]] += 1

        def team_row(team: str, home: int) -> list[int]:
            """row[r]: how much the team's waits shrink if its game in round
            `home` moves to round r (negative if they grow)."""
            rest = [r for r in played[team] if r != home]
            row = [0] * (last + 1)
            if not rest:
                return row
            size = len(rest)
            m = 0
            for to in range(1, last + 1):  # row[to] = cost of a game in `to`
                while m < size and rest[m] < to:
                    m += 1
                if m == 0:
                    row[to] = apart[rest[0] - to]
                elif m == size:
                    row[to] = apart[to - rest[-1]]
                else:
                    lo, hi = rest[m - 1], rest[m]
                    row[to] = apart[to - lo] + apart[hi - to] - apart[hi - lo]
            here = row[home]
            return [0] + [here - there for there in row[1:]]

        # part[i]: the two team rows of game i. alone[i][r]: their sum, the
        # gain from moving only game i to round r.
        part: list[tuple[list[int], list[int]]] = [([], [])] * count
        alone: list[list[int]] = [[]] * count

        def trade_gain(i: int, j: int) -> int:
            """Gain from trading the rounds of games i and j; 0 if not allowed."""
            home, away = rounds[i], rounds[j]
            if away == home:
                return 0
            near = j in rivals[i]  # then j itself is one of the games in i's way
            if blocked[i][away] != near or blocked[j][home] != near:
                return 0
            return trade_value(i, j, home, away, near)

        def trade_value(i: int, j: int, home: int, away: int, near: bool) -> int:
            """Gain from an allowed trade of game i (in `home`) and j (in `away`)."""
            if near:
                ia, ib = teams[i]
                ja, jb = teams[j]
                if ia == ja or ia == jb or ib == ja or ib == jb:
                    # A team in both games plays the same two rounds as before.
                    value = 0
                    if ia != ja and ia != jb:
                        value += part[i][0][away]
                    if ib != ja and ib != jb:
                        value += part[i][1][away]
                    if ja != ia and ja != ib:
                        value += part[j][0][home]
                    if jb != ia and jb != ib:
                        value += part[j][1][home]
                    return value
            return alone[i][away] + alone[j][home]

        def scan(i: int, used: Sequence[int]) -> tuple[int, int] | None:
            """Game i's best change as (gain, key): key is the round to move
            to, or last + 1 + j for a trade with a later game j."""
            home = rounds[i]
            mine = alone[i]
            stop = blocked[i]
            value, key = 0, -1
            for r in used:
                if r != home and not stop[r] and len(members[r]) < courts:
                    if mine[r] > value:
                        value, key = mine[r], r
            near_me = rivals[i]
            for j in range(i + 1, count):  # the same test as trade_gain
                away = rounds[j]
                if away == home:
                    continue
                near = j in near_me
                if stop[away] != near or blocked[j][home] != near:
                    continue
                gain = trade_value(i, j, home, away, near)
                if gain > value:
                    value, key = gain, last + 1 + j
            return (value, key) if key >= 0 else None

        best_of: list[tuple[int, int] | None] = [None] * count
        everything = True  # work everything out again
        stale: list[tuple[int, int]] = []  # (game, side): team rows to redo
        dirty: list[int] = []  # games whose changes may have altered
        touched: list[int] = []  # rounds whose games changed

        # Each change lowers the cost, so this ends by itself; the cap is a backstop.
        for _ in range(10 * len(rounds)):
            used = [r for r in range(1, last + 1) if members[r]]
            if everything:
                stale = [(i, side) for i in range(count) for side in (0, 1)]
            for i, side in stale:
                row = team_row(teams[i][side], rounds[i])
                part[i] = (row, part[i][1]) if side == 0 else (part[i][0], row)
            for i in sorted({i for i, _ in stale}):
                alone[i] = [x + y for x, y in zip(*part[i])]
            if everything:
                for i in range(count):
                    best_of[i] = scan(i, used)
            else:
                dirty_set = set(dirty)
                for i in range(count):
                    known = best_of[i]
                    if i in dirty_set or (
                        known is not None
                        and (
                            known[1] in touched
                            if known[1] <= last
                            else known[1] - last - 1 in dirty_set
                        )
                    ):
                        best_of[i] = scan(i, used)
                        continue
                    # Only moves into a touched round and trades with a dirty
                    # game can have altered; the rest of what is known stands.
                    value, key = known if known is not None else (0, -1)
                    home = rounds[i]
                    for r in touched:
                        if r == home or not members[r] or blocked[i][r]:
                            continue
                        if len(members[r]) >= courts:
                            continue
                        gain = alone[i][r]
                        if gain > value or (gain == value and 0 <= r < key):
                            value, key = gain, r
                    for j in dirty[bisect_right(dirty, i):]:
                        gain = trade_gain(i, j)
                        if gain > value or (gain == value and 0 <= last + 1 + j < key):
                            value, key = gain, last + 1 + j
                    best_of[i] = (value, key) if key >= 0 else None

            best: dict[int, int] = {}
            best_gain = 0
            for i in range(count):
                known = best_of[i]
                if known is not None and known[0] > best_gain:
                    best_gain, key = known
                    if key <= last:
                        best = {i: key}
                    else:
                        j = key - last - 1
                        best = {i: rounds[j], j: rounds[i]}
            everything = not best
            if not best:
                for n, a in enumerate(used):
                    for b in used[n + 1:]:
                        gain = 0
                        for here, there in ((a, b), (b, a)):
                            for g in members[here]:
                                for side in (0, 1):
                                    if there not in played[teams[g][side]]:
                                        gain += part[g][side][there]
                        if gain > best_gain:
                            best_gain = gain
                            best = {g: b for g in members[a]} | {g: a for g in members[b]}
            if not best:
                break

            touched = sorted({rounds[g] for g in best} | set(best.values()))
            for game, r in best.items():
                home = rounds[game]
                rounds[game] = r
                members[home].remove(game)
                members[r].append(game)
                for k in rivals[game]:
                    blocked[k][home] -= 1
                    blocked[k][r] += 1
                for team_id in teams[game]:
                    played[team_id].remove(home)
                    insort(played[team_id], r)
            # Rows change for every game of a team that had a game moved.
            stale = sorted(
                {
                    (g, teams[g].index(t))
                    for moved in best
                    for t in teams[moved]
                    for g in self.games_of[t]
                }
            )
            dirty = sorted(
                {g for g, _ in stale} | {g for r in touched for g in members[r]}
            )
        # Close up any round that was emptied.
        number = {r: n for n, r in enumerate(sorted(set(rounds)), start=1)}
        return [number[r] for r in rounds]
