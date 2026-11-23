import pytest

from league.models import Division, Flight, Match
from league.scheduling import generate_event
from league.setup import (SetupLocked, default_plan, delete_team, editing, refresh_grids,
                          set_weeks, step_done, sync_flights)
from tests.factories import add_flight, add_team, make_event, score

pytestmark = pytest.mark.django_db


def auto_flight(event, n, format="mens"):
    flight = add_flight(event, format=format, games=())
    flight.games_plan = ""; flight.save()
    for i in range(n):
        add_team(flight, f"{format}{i}")
    refresh_grids(event); flight.refresh_from_db()
    return flight


def test_default_plan():
    assert default_plan(4, 3) == "once"
    assert default_plan(4, 4) == "twice"
    assert default_plan(4, 7) == "custom"
    assert default_plan(5, 5) == "once"
    assert default_plan(1, 4) == "once"


def test_auto_flight_demo_size_is_twice():
    assert auto_flight(make_event(weeks=4), 4).games_per_team_by_week == [2, 2, 1, 1]


def test_preset_that_does_not_fit_stores_empty_grid():
    event = make_event(weeks=4)
    flight = auto_flight(event, 4)
    flight.games_plan = "once"; flight.save()
    refresh_grids(event); flight.refresh_from_db()
    assert flight.games_per_team_by_week == []


def test_custom_grid_cut_and_padded():
    event = make_event(weeks=4)
    flight = add_flight(event, games=(2, 3, 1, 2))       # games_plan "custom"
    set_weeks(event, 2); flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 3]
    set_weeks(event, 4); flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 3, 0, 0]


def test_withdrawn_teams_not_counted():
    from django.utils import timezone
    event = make_event(weeks=4)
    flight = auto_flight(event, 5)
    flight.teams.filter(name="mens4").update(withdrawn_at=timezone.now())
    refresh_grids(event); flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 2, 1, 1]  # 4 active teams -> twice


def test_sync_flights_add_then_confirm_remove():
    event = make_event()
    assert sync_flights(event, {("intermediate", "mens"), ("advanced", "mixed")}, confirm=False) == []
    assert {f.games_plan for f in Flight.objects.filter(division__event=event)} == {""}
    mens = Flight.objects.get(division__event=event, format="mens")
    add_team(mens, "A")
    pending = sync_flights(event, {("advanced", "mixed")}, confirm=False)
    assert [f.name for f in pending] == ["Intermediate Men's"]
    assert Flight.objects.filter(pk=mens.pk).exists()
    assert sync_flights(event, {("advanced", "mixed")}, confirm=True) == []
    assert not Division.objects.filter(event=event, level="intermediate").exists()


def test_removing_scheduled_flight_keeps_other_flights_matches():
    event = make_event(weeks=1)
    mens, mixed = auto_flight(event, 2, "mens"), auto_flight(event, 2, "mixed")
    generate_event(event)
    sync_flights(event, {("intermediate", "mixed")}, confirm=True)
    event.refresh_from_db()
    assert event.schedule_stale is True
    assert set(Match.objects.filter(flight__division__event=event).values_list("flight", flat=True)) == {mixed.pk}


def test_delete_team_with_draft_schedule():
    event = make_event(weeks=1)
    mens, mixed = auto_flight(event, 3, "mens"), auto_flight(event, 2, "mixed")
    generate_event(event)
    delete_team(mens.teams.first())
    event.refresh_from_db()
    assert event.schedule_stale is True
    assert not Match.objects.filter(flight=mens).exists() and Match.objects.filter(flight=mixed).exists()


def test_step_done():
    event = make_event(weeks=4)
    event.setup_step = 5; event.save()
    assert step_done(event) == {"basics": True, "scoring": True, "flights": False, "teams": False, "games": False}
    auto_flight(event, 4)
    assert all(step_done(event).values())


def test_editing_locks_once_scored():
    event = make_event(weeks=1)
    auto_flight(event, 2)
    generate_event(event)
    with editing(event) as locked:
        assert locked.pk == event.pk
    score(Match.objects.first())
    with pytest.raises(SetupLocked):
        with editing(event):
            pass
