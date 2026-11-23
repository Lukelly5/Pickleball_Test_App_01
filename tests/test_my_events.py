from datetime import date

import pytest

from accounts.models import Organization, User
from league.display import date_range
from league.models import Event
from tests.factories import add_flight, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db


def test_date_range():
    assert date_range(None, None) == ""
    assert date_range(date(2027, 3, 14), None) == "Mar 14"
    assert date_range(date(2027, 3, 14), date(2027, 3, 14)) == "Mar 14"
    assert date_range(date(2027, 3, 2), date(2027, 3, 23)) == "Mar 2–Mar 23"
    assert date_range(date(2026, 12, 29), date(2027, 1, 19)) == "Dec 29, 2026–Jan 19, 2027"


@pytest.fixture
def league():
    event = make_event()  # 4 weeks from 2027-03-02, org "Waco Regional"
    add_flight(event, format="mens")
    add_flight(event, format="mixed")
    return event


def test_events_table(client, league):
    Event.objects.create(organization=league.organization, name="Old Cup",
                         type="tournament", start_date=date(2026, 9, 1), courts=2)
    Event.objects.create(organization=Organization.objects.create(name="Other"),
                         name="Not Mine", type="league", start_date=date(2027, 5, 1), courts=2)
    client.force_login(admin_of(league.organization))
    response = client.get("/events/")
    rows = response.context["events"]
    assert [r.name for r in rows] == ["Spring Tuesday League", "Old Cup"]
    assert rows[0].flight_count == 2  # not multiplied by 4 weeks
    html = response.content.decode()
    assert "Mar 2–Mar 23" in html and 'data-label="Flights"' in html
    assert 'data-status="draft"' in html and "Not Mine" not in html
    assert f'href="/events/{league.pk}/' not in html  # no P4/P5 yet: plain-text rows


@pytest.mark.urls("tests.future_urls")
def test_rows_link_when_pages_exist(client, league):
    league.status = Event.Status.PUBLISHED
    league.save()
    draft = Event.objects.create(organization=league.organization, name="Draft Cup",
                                 type="tournament", start_date=date(2027, 4, 1), courts=2)
    client.force_login(admin_of(league.organization))
    html = client.get("/events/").content.decode()
    assert f'href="/events/{draft.pk}/preview/"' in html  # draft → P4
    assert f'href="/events/{league.pk}/schedule/"' in html  # published → P5
    assert 'href="/events/new/"' in html  # Create button


def test_empty_state(client):
    client.force_login(admin_of(Organization.objects.create(name="Waco Regional")))
    html = client.get("/events/").content.decode()
    assert "No events yet. Create your first league or tournament." in html


def test_admin_without_org_sees_empty_state(client):
    client.force_login(User.objects.create_superuser("root@example.com", "pw"))
    response = client.get("/events/")
    assert response.status_code == 200 and list(response.context["events"]) == []


def test_events_access(client, league):
    assert client.get("/events/").url.startswith("/login/?next=/events/")
    client.force_login(
        User.objects.create_user("p@example.com", "pw", organization=league.organization)
    )
    assert client.get("/events/").status_code == 403


def test_my_games_lists_published_teams_only(client, league):
    flight = league.divisions.get().flights.get(format="mens")
    team = add_team(flight, "Dinkers")
    player = team.players.first()
    player.email = "p@example.com"
    player.save()
    client.force_login(
        User.objects.create_user("p@example.com", "pw", organization=league.organization)
    )
    assert "You're not on any teams yet." in client.get("/me/").content.decode()  # draft hidden
    league.status = Event.Status.PUBLISHED
    league.save()
    html = client.get("/me/").content.decode()
    assert "Dinkers" in html and "Spring Tuesday League" in html


def test_my_games_requires_login(client):
    assert client.get("/me/").url.startswith("/login/?next=/me/")
