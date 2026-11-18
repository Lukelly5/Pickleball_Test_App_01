import re
import pytest
from scheduler import generate, swap_games, swap_teams, SwapConflict, Flight, Match, Schedule, Team
from tests.helpers import make_flight, make_teams

def t1(): return generate([make_flight(4, [2, 2, 2, 2])], courts=2)

def test_T6_swap_across_rounds_is_blocked():
    s = t1()
    with pytest.raises(SwapConflict) as e:
        swap_games(s, (1, 1, 1), (1, 2, 2))
    assert re.fullmatch(
        r"Can't swap: Team T\d would play on Court \d and Court \d in Round \d\.", str(e.value))

def test_swap_within_a_round_trades_courts():
    s = t1()
    before = {m.court_no: (m.team_a.id, m.team_b.id) for m in s.week(1) if m.round_no == 1}
    after_s = swap_games(s, (1, 1, 1), (1, 1, 2))
    after = {m.court_no: (m.team_a.id, m.team_b.id) for m in after_s.week(1) if m.round_no == 1}
    assert after == {1: before[2], 2: before[1]}
    assert s == t1()                                   # input untouched

def test_swap_teams_within_a_round_is_allowed():
    s = swap_teams(t1(), ((1, 1, 1), "a"), ((1, 1, 2), "a"))
    ids = [t.id for m in s.week(1) if m.round_no == 1 for t in (m.team_a, m.team_b)]
    assert sorted(ids) == ["T1", "T2", "T3", "T4"]

def test_swap_teams_across_rounds_is_blocked():
    # side "a" of court 1 is the fixed circle-method seat (same team every round),
    # so swap the "b" sides: two different teams, each already playing in the other round.
    with pytest.raises(SwapConflict) as e:
        swap_teams(t1(), ((1, 1, 1), "b"), ((1, 2, 1), "b"))
    assert re.fullmatch(
        r"Can't swap: Team T\d would play on Court 1 and Court 2 in Round 1\.", str(e.value))

def test_swap_teams_across_flights_is_blocked():
    s = generate([make_flight(4, [1], "A", "A"), make_flight(4, [1], "B", "B")], courts=4)
    a = next(m for m in s.matches if m.flight_id == "A")
    b = next(m for m in s.matches if m.flight_id == "B")
    with pytest.raises(SwapConflict) as e:
        swap_teams(s, ((a.week, a.round_no, a.court_no), "a"), ((b.week, b.round_no, b.court_no), "a"))
    assert str(e.value) == "Can't swap: teams can only play teams in their own flight."

def test_swap_across_weeks_is_blocked():
    with pytest.raises(SwapConflict) as e:
        swap_games(t1(), (1, 1, 1), (2, 1, 1))
    assert str(e.value) == "Can't swap: games must be in the same week."

def test_missing_slot():
    with pytest.raises(KeyError):
        swap_games(t1(), (1, 9, 9), (1, 1, 1))

def test_swapping_a_slot_with_itself_is_a_no_op():
    s = t1()
    assert swap_games(s, (1, 1, 1), (1, 1, 1)) == s
    assert swap_teams(s, ((1, 1, 1), "a"), ((1, 1, 1), "a")) == s

def test_team_swapped_into_its_own_match_reports_same_court_pair():
    s = t1()
    m1 = next(m for m in s.matches if (m.week, m.round_no, m.court_no) == (1, 1, 1))
    # a later match that contains m1's team_b; swap m1.team_a with that team
    m2 = next(m for m in s.matches
              if m.week == 1 and m.round_no == 2 and m1.team_b.id in (m.team_a.id, m.team_b.id))
    side = "a" if m2.team_a.id == m1.team_b.id else "b"
    with pytest.raises(SwapConflict) as e:
        swap_teams(s, ((1, 1, 1), "a"), ((1, 2, m2.court_no), side))
    assert str(e.value) == (
        f"Can't swap: Team {m1.team_b.name} would play on Court 1 and Court 1 in Round 1.")

def test_team_clash_message_says_team_then_the_name():
    d, a, b, c = (Team(x, x, (f"{x}-1", f"{x}-2")) for x in ("Dinkers", "A", "B", "C"))
    s = Schedule((Match("F", 1, 1, 1, d, a), Match("F", 1, 1, 2, b, c),
                  Match("F", 1, 2, 1, d, b), Match("F", 1, 2, 2, a, c)), courts=2)
    with pytest.raises(SwapConflict) as e:
        swap_games(s, (1, 1, 2), (1, 2, 1))
    assert str(e.value).startswith("Can't swap: Team Dinkers would play on Court")
    assert str(e.value) == "Can't swap: Team Dinkers would play on Court 1 and Court 2 in Round 1."

def test_player_clash_message_names_the_player_without_a_prefix():
    mens = list(make_teams(4, "M")); mixed = list(make_teams(4, "X"))
    mens[0] = Team("M1", "M1", ("pat", "M1-b"))
    mixed[0] = Team("X1", "X1", ("pat", "X1-b"))
    s = generate([Flight("men", "Int Men's", tuple(mens), (1,)),
                  Flight("mix", "Int Mixed", tuple(mixed), (1,))], courts=4)
    def has_pat(m): return "pat" in m.team_a.players + m.team_b.players
    late = next(m for m in s.matches if has_pat(m) and m.round_no == 2)
    early = next(m for m in s.matches if not has_pat(m) and m.round_no == 1)
    with pytest.raises(SwapConflict) as e:
        swap_games(s, (1, 2, late.court_no), (1, 1, early.court_no))
    assert re.fullmatch(
        r"Can't swap: pat would play on Court \d and Court \d in Round 1\.", str(e.value))

@pytest.mark.parametrize("sides", [("a", "x"), ("left", "b"), ("A", "b"), ("a", "")])
def test_swap_teams_rejects_an_unknown_side(sides):
    with pytest.raises(ValueError) as e:
        swap_teams(t1(), ((1, 1, 1), sides[0]), ((1, 1, 2), sides[1]))
    assert not isinstance(e.value, SwapConflict)
    assert "'a' or 'b'" in str(e.value)
