from collections import Counter
import pytest
from scheduler.pairings import weekly_rotations, round_robin_preset
from scheduler.types import ScheduleError
from tests.helpers import make_flight

def games_per_team(week):  # week = list of rotations
    return Counter(t.id for rot in week for p in rot for t in p)

# PRD T7
@pytest.mark.parametrize("n", range(4, 13))
@pytest.mark.parametrize("g", [1, 2, 3])
def test_T7_nobody_gets_an_empty_night(n, g):
    flight = make_flight(n, [g] * 4)
    for week in weekly_rotations(flight):
        counts = games_per_team(week)
        per_team = [counts.get(t.id, 0) for t in flight.teams]
        if n % 2 == 0:
            assert set(per_team) == {g}
        else:
            assert set(per_team) <= {g, g - 1}
            if g >= 2:
                assert min(per_team) >= 1

# PRD T9
def test_T9_rotating_bye():
    flight = make_flight(5, [1] * 5)
    weeks = weekly_rotations(flight)
    sat_out = []
    for week in weeks:
        assert sum(len(r) for r in week) == 2
        playing = set(games_per_team(week))
        sat_out += [t.id for t in flight.teams if t.id not in playing]
    assert sorted(sat_out) == sorted(t.id for t in flight.teams)
    pairs = Counter(frozenset(t.id for t in p) for w in weeks for r in w for p in r)
    assert len(pairs) == 10 and set(pairs.values()) == {1}

@pytest.mark.parametrize("n,games", [(4, [2, 2, 2, 2]), (6, [3, 1, 2, 3]), (5, [2, 2, 2])])
def test_every_pair_meets_k_times_before_any_meets_k_plus_1(n, games):
    flight = make_flight(n, games)
    pairs = Counter()
    for week in weekly_rotations(flight):
        for rot in week:
            pairs.update(frozenset(t.id for t in p) for p in rot)
            total_pairs = n * (n - 1) // 2
            values = list(pairs.values()) + [0] * (total_pairs - len(pairs))
            # only checked at cycle granularity: spread never exceeds 1
            assert max(values) - min(values) <= 1

def test_zero_games_week_is_empty_and_does_not_advance():
    a = weekly_rotations(make_flight(4, [1, 0, 1]))
    b = weekly_rotations(make_flight(4, [1, 1]))
    assert a[1] == [] and a[2] == b[1]

def test_preset_values():
    assert round_robin_preset(4, 3, 1) == (1, 1, 1)
    assert round_robin_preset(6, 4, 1) == (2, 1, 1, 1)
    assert round_robin_preset(4, 4, 2) == (2, 2, 1, 1)
    assert round_robin_preset(5, 5, 1) == (1, 1, 1, 1, 1)

def test_preset_blocks_an_empty_week():
    with pytest.raises(ScheduleError) as e:
        round_robin_preset(4, 4, 1)
    assert str(e.value) == (
        "Round robin once is 3 games per team, but you have 4 weeks. "
        "Week 4 has no games — reduce weeks or choose twice."
    )

def test_preset_is_part_of_the_public_package():
    import scheduler
    assert scheduler.round_robin_preset is round_robin_preset
    assert "round_robin_preset" in scheduler.__all__

@pytest.mark.parametrize("n_teams,weeks,times,message", [
    (4, 0, 1, "Weeks must be at least 1."),
    (4, -2, 1, "Weeks must be at least 1."),
    (1, 3, 1, "A round robin needs at least 2 teams."),
    (0, 3, 1, "A round robin needs at least 2 teams."),
    (4, 3, 0, "A round robin preset is played once or twice."),
    (4, 3, 3, "A round robin preset is played once or twice."),
])
def test_preset_rejects_bad_numbers(n_teams, weeks, times, message):
    with pytest.raises(ScheduleError) as e:
        round_robin_preset(n_teams, weeks, times)
    assert str(e.value) == message
