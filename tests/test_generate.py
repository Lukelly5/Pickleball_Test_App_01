from collections import Counter, defaultdict
from math import ceil
import pytest
from scheduler import generate, Flight, Team, ScheduleError
from tests.helpers import make_flight, make_teams

def assert_hard_rules(s):
    slots = Counter((m.week, m.round_no, m.court_no) for m in s.matches)
    assert set(slots.values()) <= {1}                      # one game per court per round
    assert all(1 <= m.court_no <= s.courts for m in s.matches)
    busy = defaultdict(list)
    for m in s.matches:
        busy[(m.week, m.round_no)] += [*m.team_a.players, *m.team_b.players]
    for players in busy.values():
        assert len(players) == len(set(players))           # no player twice in a round

def per_team(matches):
    return Counter(t.id for m in matches for t in (m.team_a, m.team_b))

def pair_counts(matches):
    return Counter(frozenset((m.team_a.id, m.team_b.id)) for m in matches)

def test_T1_swish_example():
    s = generate([make_flight(4, [2, 2, 2, 2])], courts=2)
    assert_hard_rules(s)
    assert len(s.matches) == 16
    for w in range(1, 5):
        wk = s.week(w)
        assert {(m.round_no, m.court_no) for m in wk} == {(1, 1), (1, 2), (2, 1), (2, 2)}
        assert set(per_team(wk).values()) == {2}
    assert set(per_team(s.matches).values()) == {8}
    assert sorted(pair_counts(s.matches).values()) == [2, 2, 3, 3, 3, 3]

def test_T2_different_numbers_week_to_week():
    s = generate([make_flight(10, [1, 2])], courts=5)
    assert_hard_rules(s)
    assert len(s.week(1)) == 5 and max(m.round_no for m in s.week(1)) == 1
    assert len(s.week(2)) == 10 and max(m.round_no for m in s.week(2)) == 2
    assert set(per_team(s.week(1)).values()) == {1}
    assert set(per_team(s.week(2)).values()) == {2}
    assert set(pair_counts(s.matches).values()) == {1}

def test_T4_odd_teams():
    s = generate([make_flight(5, [5])], courts=2)
    assert_hard_rules(s)
    assert len(s.matches) == 10
    assert max(m.round_no for m in s.matches) == 5
    assert set(per_team(s.matches).values()) == {4}
    assert set(pair_counts(s.matches).values()) == {1}

def test_T5_player_in_two_flights():
    mens = list(make_teams(4, "M")); mixed = list(make_teams(4, "X"))
    mens[0] = Team("M1", "Team M1", ("pat", "M1-b"))
    mixed[0] = Team("X1", "Team X1", ("pat", "X1-b"))
    s = generate([Flight("men", "Int Men's", tuple(mens), (1,)),
                  Flight("mix", "Int Mixed", tuple(mixed), (1,))], courts=4)
    assert_hard_rules(s)
    pats = [m.round_no for m in s.matches if "pat" in m.team_a.players + m.team_b.players]
    assert sorted(pats) == [1, 2]
    assert max(m.round_no for m in s.matches) == 2

def test_T8_short_sits():
    s = generate([make_flight(6, [2])], courts=2)
    assert_hard_rules(s)
    assert max(m.round_no for m in s.matches) == 3
    rounds = defaultdict(list)
    for m in s.matches:
        rounds[m.team_a.id].append(m.round_no); rounds[m.team_b.id].append(m.round_no)
    assert all(max(r) - min(r) - 1 <= 1 for r in rounds.values())

def test_flights_are_interleaved():
    s = generate([make_flight(4, [1], "A", "A"), make_flight(4, [1], "B", "B")], courts=2)
    assert {m.flight_id for m in s.matches if m.round_no == 1} == {"A", "B"}

@pytest.mark.parametrize("n", range(2, 13))
@pytest.mark.parametrize("courts", [1, 2, 3, 5])
def test_hard_rules_hold_everywhere(n, courts):
    s = generate([make_flight(n, [2, 1, 3])], courts=courts)
    assert_hard_rules(s)

def test_one_court_gives_every_game_its_own_round():
    s = generate([make_flight(4, [2])], courts=1)
    assert sorted(m.round_no for m in s.matches) == [1, 2, 3, 4]

def test_same_inputs_same_schedule():
    args = ([make_flight(7, [2, 3, 1])], 3)
    assert generate(*args) == generate(*args)

def test_too_few_teams():
    with pytest.raises(ScheduleError) as e:
        generate([Flight("f", "Intermediate Mixed", make_teams(1), (1,))], courts=2)
    assert str(e.value) == "Add at least 2 teams to Intermediate Mixed before generating."

def test_player_on_two_teams_in_one_flight():
    teams = (Team("a", "A", ("pat", "x")), Team("b", "B", ("pat", "y")))
    with pytest.raises(ScheduleError) as e:
        generate([Flight("f", "Int Men's", teams, (1,))], courts=2)
    assert str(e.value) == "pat is on two teams in Int Men's."

@pytest.mark.parametrize("flights,courts", [
    ([make_flight(4, [1])], 0),                                   # no courts
    ([make_flight(4, [-1])], 2),                                  # negative games
    ([make_flight(4, [1, 1], "A", "A"), make_flight(4, [1], "B", "B")], 2),  # week counts differ
    ([make_flight(4, [1]), make_flight(4, [1])], 2),              # duplicate flight / team ids
])
def test_invalid_inputs_raise(flights, courts):
    with pytest.raises(ScheduleError):
        generate(flights, courts)


def longest_sit(matches):
    rounds = defaultdict(list)
    for m in matches:
        rounds[m.team_a.id].append(m.round_no); rounds[m.team_b.id].append(m.round_no)
    return max(b - a - 1 for r in rounds.values() for a, b in zip(sorted(r), sorted(r)[1:]))

# teams, games per team, courts -> longest sit the placement must not exceed
@pytest.mark.parametrize("n,games,courts,bound", [
    (8, 2, 2, 1),
    (10, 2, 2, 1),
    (12, 2, 2, 1),
    (12, 3, 2, 1),
    (12, 2, 3, 1),
    (9, 3, 2, 1),
    (12, 2, 1, 1),
])
def test_games_sit_close_together_when_courts_are_short(n, games, courts, bound):
    s = generate([make_flight(n, [games])], courts=courts)
    assert_hard_rules(s)
    assert longest_sit(s.matches) <= bound

def shared_player_flights(games):
    a = list(make_teams(6, "A")); b = list(make_teams(6, "B"))
    a[0] = Team("A1", "A1", ("pat", "A1-b"))
    b[0] = Team("B1", "B1", ("pat", "B1-b"))
    return [Flight("A", "Flight A", tuple(a), (games,)),
            Flight("B", "Flight B", tuple(b), (games,))]

def test_shared_player_does_not_spread_the_other_teams_out():
    # pat plays 4 games, so the night needs 4 rounds; nobody should sit in between
    s = generate(shared_player_flights(2), courts=6)
    assert_hard_rules(s)
    assert max(m.round_no for m in s.matches) == 4
    assert longest_sit(s.matches) == 0

# A night can't be shorter than this: only min(courts, teams // 2) games fit
# in a round, and a team needs a round for each of its games.
@pytest.mark.parametrize("n", range(2, 13))
@pytest.mark.parametrize("games", [1, 2, 3, 5])
@pytest.mark.parametrize("courts", [1, 2, 3, 4, 6])
def test_night_is_as_short_as_possible(n, games, courts):
    s = generate([make_flight(n, [games])], courts=courts)
    assert_hard_rules(s)
    most_by_a_team = max(per_team(s.matches).values())
    shortest = max(ceil(len(s.matches) / min(courts, n // 2)), most_by_a_team)
    assert max(m.round_no for m in s.matches) == shortest
    assert set(m.round_no for m in s.matches) == set(range(1, shortest + 1))

def test_twelve_teams_five_games_two_courts_is_quick():
    import time
    start = time.perf_counter()
    generate([make_flight(12, [5])], courts=2)
    assert time.perf_counter() - start < 1

def test_same_team_id_in_two_flights():
    with pytest.raises(ScheduleError) as e:
        generate([make_flight(4, [1], "A", "T"), make_flight(4, [1], "B", "T")], courts=2)
    assert str(e.value) == "Team id T1 is used more than once."

def test_same_player_twice_on_one_team():
    teams = (Team("a", "Aces", ("pat", "pat")), Team("b", "Bangers", ("x", "y")))
    with pytest.raises(ScheduleError) as e:
        generate([Flight("f", "Int Men's", teams, (1,))], courts=2)
    assert str(e.value) == "pat is listed twice on Aces."

# PRD T7, through the whole generator
@pytest.mark.parametrize("n", range(4, 13))
@pytest.mark.parametrize("g", [1, 2, 3])
def test_T7_nobody_gets_an_empty_night(n, g):
    flight = make_flight(n, [g] * 4)
    s = generate([flight], courts=3)
    assert_hard_rules(s)
    for w in range(1, 5):
        counts = per_team(s.week(w))
        played = [counts.get(t.id, 0) for t in flight.teams]
        if n % 2 == 0:
            assert set(played) == {g}
        else:
            assert set(played) <= {g, g - 1}
            if g >= 2:
                assert min(played) >= 1

# PRD T9, through the whole generator
def test_T9_rotating_bye():
    flight = make_flight(5, [1] * 5)
    s = generate([flight], courts=2)
    assert_hard_rules(s)
    sat_out = []
    for w in range(1, 6):
        assert len(s.week(w)) == 2
        playing = set(per_team(s.week(w)))
        sat_out += [t.id for t in flight.teams if t.id not in playing]
    assert sorted(sat_out) == sorted(t.id for t in flight.teams)
    pairs = pair_counts(s.matches)
    assert len(pairs) == 10 and set(pairs.values()) == {1}

@pytest.mark.parametrize("make", [
    lambda: ([make_flight(4, [2, 2, 2, 2])], 2),
    lambda: ([make_flight(12, [2])], 1),
    lambda: ([make_flight(9, [3, 0, 4])], 2),
    lambda: ([make_flight(12, [5, 3])], 2),
    lambda: ([make_flight(5, [2, 1], "A", "A"), make_flight(8, [3, 2], "B", "B")], 3),
    lambda: (shared_player_flights(3), 4),
    lambda: ([make_flight(11, [4]), make_flight(6, [5], "B", "B"), make_flight(3, [2], "C", "C")], 5),
])
def test_same_inputs_same_schedule_for_varied_inputs(make):
    (flights, courts), (again, _) = make(), make()
    first, second = generate(flights, courts), generate(again, courts)
    assert first == second
    assert first.matches == second.matches
    assert_hard_rules(first)
