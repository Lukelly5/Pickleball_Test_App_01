from scheduler import generate, fairness_report
from tests.helpers import make_flight

def test_T1_numbers():
    f = make_flight(4, [2, 2, 2, 2])
    r = fairness_report(generate([f], 2), [f])
    assert all(set(r.games_by_week[w].values()) == {2} for w in range(1, 5))
    assert set(r.games_total.values()) == {8}
    assert sorted(r.pair_counts.values()) == [2, 2, 3, 3, 3, 3]
    assert all(v == 0 for wk in r.longest_sit.values() for v in wk.values())

def test_bye_team_shows_zero_not_missing():
    f = make_flight(5, [1])
    r = fairness_report(generate([f], 2), [f])
    assert sorted(r.games_by_week[1].values()) == [0, 1, 1, 1, 1]

def test_unmet_pairs_show_zero():
    f = make_flight(6, [1])
    r = fairness_report(generate([f], 3), [f])
    assert len(r.pair_counts) == 15 and sorted(r.pair_counts.values()).count(0) == 12

def test_longest_sit_counts_idle_rounds():
    f = make_flight(6, [2])
    r = fairness_report(generate([f], 2), [f])
    assert max(r.longest_sit[1].values()) == 1
