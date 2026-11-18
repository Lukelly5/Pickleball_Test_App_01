import pytest
from scheduler import generate, fairness_report, summary_line, Match, Schedule
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

def test_longest_sit_on_a_hand_built_schedule():
    a, b, c, d = make_flight(4, [2]).teams
    f = make_flight(4, [2])
    s = Schedule((Match("F1", 1, 1, 1, a, b), Match("F1", 1, 2, 1, c, d),
                  Match("F1", 1, 3, 1, b, c), Match("F1", 1, 4, 1, a, d)), courts=1)
    r = fairness_report(s, [f])
    assert r.longest_sit[1] == {"T1": 2, "T2": 1, "T3": 0, "T4": 1}

def test_summary_line_T1():
    f = make_flight(4, [2, 2, 2, 2])
    r = fairness_report(generate([f], 2), [f])
    assert summary_line(r, f) == "16 games · 8 per team · every pair meets 2–3 times"

@pytest.mark.parametrize("n,games,expected", [
    (2, [1], "1 game · 1 per team · every pair meets once"),
    (2, [2], "2 games · 2 per team · every pair meets twice"),
    (2, [1, 1, 1], "3 games · 3 per team · every pair meets 3 times"),
    (4, [3], "6 games · 3 per team · every pair meets once"),
    (5, [1], "2 games · 0–1 per team · every pair meets 0–1 times"),
])
def test_summary_line_wording(n, games, expected):
    f = make_flight(n, games)
    r = fairness_report(generate([f], 2), [f])
    assert summary_line(r, f) == expected

def test_summary_line_is_per_flight():
    a, b = make_flight(4, [1], "A", "A"), make_flight(6, [1], "B", "B")
    r = fairness_report(generate([a, b], 3), [a, b])
    assert summary_line(r, a) == "2 games · 1 per team · every pair meets 0–1 times"
    assert summary_line(r, b) == "3 games · 1 per team · every pair meets 0–1 times"
