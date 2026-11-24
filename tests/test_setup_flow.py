import pytest

from accounts.models import Organization
from league.models import Event, Flight, Match
from league.setup import step_done
from tests.factories import admin_of

pytestmark = pytest.mark.django_db


def test_full_setup_walkthrough(client):
    client.force_login(admin_of(Organization.objects.create(name="Fresh Org")))

    response = client.post("/events/new/", {
        "name": "Demo League", "start_date": "2027-03-02", "weeks": "4", "courts": "2", "nav": "next"})
    event = Event.objects.get(name="Demo League")
    base = f"/events/{event.pk}/setup"
    assert response.url == f"{base}/scoring/"

    response = client.post(f"{base}/scoring/", {
        "match_format": event.match_format, "points_to_win": event.points_to_win,
        **({"win_by_two": "on"} if event.win_by_two else {}), "nav": "next"})
    assert response.url == f"{base}/flights/"

    response = client.post(f"{base}/flights/", {"cells": ["intermediate:mens", "intermediate:mixed"], "nav": "next"})
    assert response.url == f"{base}/teams/"

    flights = list(Flight.objects.filter(division__event=event))
    assert len(flights) == 2
    for flight in flights:
        for n in "ABCD":
            response = client.post(f"{base}/teams/?flight={flight.pk}", {
                "action": "save_team", "flight": flight.pk, "name": f"{flight.format} {n}",
                "player1": f"{flight.format} {n} One", "player1_email": f"{flight.format}{n}1@example.com",
                "player2": f"{flight.format} {n} Two", "player2_email": f"{flight.format}{n}2@example.com"})
            assert response.status_code == 302
    assert client.post(f"{base}/teams/", {"nav": "next"}).url == f"{base}/games/"

    data = {"nav": "stay"}
    for flight in flights:
        data[f"f{flight.pk}-plan"] = "twice"
        data.update({f"f{flight.pk}-w{i}": "1" for i in range(1, 5)})  # the grid inputs the page always posts
    page = client.get(f"{base}/games/").content.decode()
    assert "Each team plays every other team:" in page
    assert client.post(f"{base}/games/", data).status_code == 200  # "stay" re-renders the step

    response = client.post(f"{base}/games/generate/", data, follow=True)
    assert response.redirect_chain[-1][0] == "/events/"
    assert "Schedule drafted · 24 games over 4 weeks" in [str(m) for m in response.context["messages"]]
    assert Match.objects.filter(flight__division__event=event).count() == 24
    event.refresh_from_db()
    assert all(step_done(event).values())
    assert f'href="/events/{event.pk}/setup/"' in response.content.decode()
