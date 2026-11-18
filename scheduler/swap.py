from dataclasses import replace

from scheduler.types import Match, Schedule, ScheduleError, Team

Slot = tuple[int, int, int]  # (week, round_no, court_no)


class SwapConflict(ScheduleError):
    pass


def _find(schedule: Schedule, slot: Slot) -> Match:
    for m in schedule.matches:
        if (m.week, m.round_no, m.court_no) == slot:
            return m
    raise KeyError(slot)


def _clash(a: Match, b: Match) -> str | None:
    """Who is double-booked between two matches (or within one when a is b):
    "Team <name>" for a team, or the player's name when two different teams
    share a player."""
    if a is b:
        if a.team_a.id == a.team_b.id:
            return f"Team {a.team_a.name}"
        return None
    for ta in (a.team_a, a.team_b):
        for tb in (b.team_a, b.team_b):
            if ta.id == tb.id:
                return f"Team {ta.name}"
    for ta in (a.team_a, a.team_b):
        for tb in (b.team_a, b.team_b):
            for player in ta.players:
                if player in tb.players:
                    return player
    return None


def _check_week(schedule: Schedule, week: int) -> None:
    rounds: dict[int, list[Match]] = {}
    for m in schedule.week(week):
        rounds.setdefault(m.round_no, []).append(m)
    for round_no in sorted(rounds):
        in_round = sorted(rounds[round_no], key=lambda m: m.court_no)
        for i, a in enumerate(in_round):
            for b in in_round[i:]:
                who = _clash(a, b)
                if who is not None:
                    raise SwapConflict(
                        f"Can't swap: {who} would play on Court {a.court_no} "
                        f"and Court {b.court_no} in Round {round_no}."
                    )


def swap_games(schedule: Schedule, a: Slot, b: Slot) -> Schedule:
    ma, mb = _find(schedule, a), _find(schedule, b)
    if a == b:
        return schedule
    if ma.week != mb.week:
        raise SwapConflict("Can't swap: games must be in the same week.")
    moved_a = replace(ma, round_no=mb.round_no, court_no=mb.court_no)
    moved_b = replace(mb, round_no=ma.round_no, court_no=ma.court_no)
    matches = [m for m in schedule.matches if m is not ma and m is not mb]
    candidate = Schedule(tuple(matches) + (moved_a, moved_b), schedule.courts)
    _check_week(candidate, ma.week)
    return candidate


def swap_teams(
    schedule: Schedule, a: tuple[Slot, str], b: tuple[Slot, str]
) -> Schedule:
    (slot_a, side_a), (slot_b, side_b) = a, b
    for side in (side_a, side_b):
        if side not in ("a", "b"):
            raise ValueError(f"Side must be 'a' or 'b', not {side!r}.")
    ma, mb = _find(schedule, slot_a), _find(schedule, slot_b)
    if a == b:
        return schedule
    if ma.week != mb.week:
        raise SwapConflict("Can't swap: games must be in the same week.")
    if ma.flight_id != mb.flight_id:
        raise SwapConflict(
            "Can't swap: teams can only play teams in their own flight."
        )
    team_a: Team = ma.team_a if side_a == "a" else ma.team_b
    team_b: Team = mb.team_a if side_b == "a" else mb.team_b

    def put(m: Match, side: str, team: Team) -> Match:
        return replace(m, **{"team_a" if side == "a" else "team_b": team})

    if ma is mb:
        new_ma = put(put(ma, side_a, team_b), side_b, team_a)
        replacements = {id(ma): new_ma}
    else:
        replacements = {
            id(ma): put(ma, side_a, team_b),
            id(mb): put(mb, side_b, team_a),
        }
    matches = tuple(replacements.get(id(m), m) for m in schedule.matches)
    candidate = Schedule(matches, schedule.courts)
    _check_week(candidate, ma.week)
    return candidate
