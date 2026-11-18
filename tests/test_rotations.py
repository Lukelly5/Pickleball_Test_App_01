from collections import Counter

import pytest

from scheduler.pairings import rotations
from tests.helpers import make_teams


def pair(p):
    return frozenset(t.id for t in p)


@pytest.mark.parametrize("n", range(2, 13))
def test_full_cycle_is_a_round_robin(n):
    rots = rotations(make_teams(n))
    assert len(rots) == (n - 1 if n % 2 == 0 else n)
    all_pairs = Counter(pair(p) for r in rots for p in r)
    assert len(all_pairs) == n * (n - 1) // 2
    assert set(all_pairs.values()) == {1}


@pytest.mark.parametrize("n", range(2, 13))
def test_each_rotation_uses_each_team_at_most_once(n):
    for r in rotations(make_teams(n)):
        ids = [t.id for p in r for t in p]
        assert len(ids) == len(set(ids))
        assert len(r) == n // 2


@pytest.mark.parametrize("n", [3, 5, 7, 9, 11])
def test_odd_counts_give_each_team_exactly_one_bye_per_cycle(n):
    teams = make_teams(n)
    byes = []
    for r in rotations(teams):
        playing = {t.id for p in r for t in p}
        byes += [t.id for t in teams if t.id not in playing]
    assert sorted(byes) == sorted(t.id for t in teams)


def test_two_teams_is_one_rotation_of_one_game():
    assert [len(r) for r in rotations(make_teams(2))] == [1]


def test_same_input_same_output():
    assert rotations(make_teams(7)) == rotations(make_teams(7))
