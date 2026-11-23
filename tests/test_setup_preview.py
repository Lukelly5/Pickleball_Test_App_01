import pytest

from league.models import Flight
from league.setup import refresh_grids
from league.setup_preview import plan_views
from tests.factories import add_flight, add_team, make_event

pytestmark = pytest.mark.django_db


def flight_with(event, n, games, plan="custom", format="mens"):
    flight = add_flight(event, format=format, games=games)
    flight.games_plan = plan; flight.save()
    for i in range(n):
        add_team(flight, f"{format}{i}")
    refresh_grids(event); flight.refresh_from_db()
    return flight


def test_summary_for_custom_grid():
    event = make_event(weeks=4, courts=2)
    flight_with(event, 4, (1, 1, 1, 1))
    (view,), error = plan_views(event)
    assert error is None and view.blocker is None and view.total == 4
    assert view.summary == "8 games · 4 per team · every pair meets 1–2 times"


def test_odd_team_note_and_preset_grid():
    event = make_event(weeks=4, courts=2)
    flight_with(event, 5, (), plan="")
    (view,), _ = plan_views(event)
    assert view.plan == "once" and view.grid == [2, 1, 1, 1]
    assert view.notes[0] == "5 teams: one team sits out each round, so each week one team plays 1 fewer. Byes rotate."


def test_long_night_counts_every_flight_on_the_courts():
    event = make_event(weeks=1, courts=2)
    flight_with(event, 4, (1,), format="mens")
    flight_with(event, 4, (1,), format="mixed")
    views, _ = plan_views(event)
    for view in views:
        assert view.notes == ["Week 1: each team plays 1 game. On 2 courts that takes 2 rounds."]


def test_blockers():
    event = make_event(weeks=4)
    flight_with(event, 1, (1, 1, 1, 1))
    (view,), _ = plan_views(event)
    assert view.blocker == "Add at least 2 teams to Intermediate Men's before generating." and view.summary is None
    flight = Flight.objects.get()
    flight.teams.first().members.first().delete()
    add_team(flight, "Second")
    (view,), _ = plan_views(event)
    assert view.blocker == "mens0 needs exactly 2 players before generating."


def test_preset_error_blocks():
    event = make_event(weeks=4)
    flight_with(event, 4, (), plan="once")
    (view,), _ = plan_views(event)
    assert view.blocker == ("Round robin once is 3 games per team, but you have 4 weeks. "
                            "Week 4 has no games — reduce weeks or choose twice.")


def test_overrides_are_not_saved_and_zero_weeks_flagged():
    event = make_event(weeks=4)
    flight = flight_with(event, 4, (1, 1, 1, 1))
    (view,), _ = plan_views(event, {flight.pk: ("custom", [2, 2, 0, 0])})
    assert view.grid == [2, 2, 0, 0] and view.empty_weeks == [3, 4]
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [1, 1, 1, 1]
