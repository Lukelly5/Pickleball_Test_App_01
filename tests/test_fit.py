import pytest
from scheduler import check_fit, fit_message, ScheduleError
from tests.helpers import make_flight

def test_T3_does_not_fit():
    r = check_fit([make_flight(8, [7])], courts=4, game_minutes=15, window_minutes=60)
    assert (r.games, r.rounds, r.minutes, r.fits) == (28, 7, 105, False)
    assert (r.rounds_that_fit, r.suggested_games_per_team) == (4, 4)
    assert fit_message(r) == (
        "28 games need 7 rounds on 4 courts (~1h 45m). Your 60-minute window fits 4 rounds. "
        "Add courts, extend the window, or lower games per team to 4.")

def test_T3_fits_at_four_games_per_team():
    r = check_fit([make_flight(8, [4])], courts=4, game_minutes=15, window_minutes=60)
    assert (r.games, r.rounds, r.fits, r.suggested_games_per_team) == (16, 4, True, None)

def test_fits_message():
    r = check_fit([make_flight(8, [7])], courts=4, game_minutes=15, window_minutes=120)
    assert fit_message(r) == (
        "28 games · 7 rounds on 4 courts · about 1h 45m. Fits your 2-hour window.")

def test_nothing_fits():
    r = check_fit([make_flight(8, [7])], courts=1, game_minutes=15, window_minutes=30)
    assert r.fits is False and r.suggested_games_per_team is None
    assert fit_message(r).endswith("Add courts or extend the window.")

def test_leagues_are_rejected():
    with pytest.raises(ScheduleError):
        check_fit([make_flight(4, [1, 1])], 2, 15, 60)

@pytest.mark.parametrize("game_minutes,window_minutes", [(0, 60), (15, 0)])
def test_nonpositive_minutes_are_rejected(game_minutes, window_minutes):
    with pytest.raises(ScheduleError):
        check_fit([make_flight(4, [1])], 2, game_minutes, window_minutes)

def test_singular_words_when_it_fits():
    r = check_fit([make_flight(2, [1])], courts=1, game_minutes=15, window_minutes=60)
    assert fit_message(r) == "1 game · 1 round on 1 court · about 15m. Fits your 60-minute window."

def test_singular_round_in_the_window():
    r = check_fit([make_flight(4, [1])], courts=1, game_minutes=15, window_minutes=20)
    assert fit_message(r) == (
        "2 games need 2 rounds on 1 court (~30m). Your 20-minute window fits 1 round. "
        "Add courts or extend the window.")

def test_window_shorter_than_one_game():
    r = check_fit([make_flight(2, [1])], courts=1, game_minutes=15, window_minutes=10)
    assert (r.fits, r.rounds_that_fit, r.suggested_games_per_team) == (False, 0, None)
    assert fit_message(r) == (
        "1 game needs 1 round on 1 court (~15m). Your 10-minute window fits 0 rounds. "
        "Extend the window.")

def test_adding_courts_is_not_suggested_when_no_round_fits():
    r = check_fit([make_flight(8, [7])], courts=4, game_minutes=15, window_minutes=10)
    assert fit_message(r).endswith("fits 0 rounds. Extend the window.")
