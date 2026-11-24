import pytest

from league.models import Flight, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db


@pytest.fixture
def event(client):
    event = make_event()
    client.force_login(admin_of(event.organization))
    return event


def url(event):
    return f"/events/{event.pk}/setup/flights/"


def test_grid_and_save(client, event):
    html = client.get(url(event)).content.decode()
    assert html.count('name="cells"') == 9
    response = client.post(url(event), {"cells": ["intermediate:mens", "advanced:mixed"], "nav": "next"})
    assert response.url == f"/events/{event.pk}/setup/teams/"
    assert sorted(f.name for f in Flight.objects.filter(division__event=event)) == ["Advanced Mixed", "Intermediate Men's"]
    event.refresh_from_db()
    assert event.setup_step == 3


def test_none_ticked(client, event):
    assert "Pick at least one flight." in client.post(url(event), {"nav": "next"}).content.decode()


def test_existing_flights_preticked(client, event):
    add_flight(event, format="mens")
    html = client.get(url(event)).content.decode()
    assert html.count("checked") == 1


def test_remove_flight_with_teams_needs_confirm(client, event):
    flight = add_flight(event, format="mens")
    add_team(flight, "A"); add_team(flight, "B")
    html = client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next"}).content.decode()
    assert "Removing Intermediate Men's deletes its 2 teams." in html
    assert Flight.objects.filter(pk=flight.pk).exists()
    client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next", "confirm": "1"})
    assert not Flight.objects.filter(pk=flight.pk).exists()


def test_singular_team(client, event):
    flight = add_flight(event, format="mens")
    add_team(flight, "A")
    html = client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next"}).content.decode()
    assert "Removing Intermediate Men's deletes its 1 team." in html


def test_locked(client, event):
    flight = add_flight(event, games=(1, 1, 1, 1))
    add_team(flight, "A"); add_team(flight, "B")
    generate_event(event); score(Match.objects.first())
    response = client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next"}, follow=True)
    assert "Scores have been entered, so the setup is locked." in response.content.decode()
    assert Flight.objects.filter(pk=flight.pk).exists()
    html = client.get(url(event)).content.decode()
    assert "disabled" in html


@pytest.mark.parametrize("nav, target", [("next", "teams"), ("back", "scoring"), ("goto:games", "games")])
def test_locked_still_navigates(client, event, nav, target):
    flight = add_flight(event, games=(1, 1, 1, 1))
    add_team(flight, "A"); add_team(flight, "B")
    generate_event(event); score(Match.objects.first())
    response = client.post(url(event), {"cells": ["advanced:mixed"], "nav": nav})
    assert response.status_code == 302 and response.url == f"/events/{event.pk}/setup/{target}/"
    assert Flight.objects.filter(pk=flight.pk).exists()

