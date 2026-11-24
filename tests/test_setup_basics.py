from datetime import date

import pytest

from accounts.models import Organization, User
from league.models import Event, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db
BASICS = {"name": "Fall League", "start_date": "2027-09-07", "weeks": "4", "courts": "2", "nav": "next"}


@pytest.fixture
def admin(client):
    user = admin_of(Organization.objects.get_or_create(name="Waco Regional")[0])
    client.force_login(user)
    return user


def test_create_league(client, admin):
    page = client.get("/events/new/").content.decode()
    assert "Create league" in page and "Basics" in page
    response = client.post("/events/new/", BASICS)
    event = Event.objects.get(name="Fall League")
    assert response.url == f"/events/{event.pk}/setup/scoring/"
    assert (event.type, event.status, event.setup_step, event.organization) == ("league", "draft", 1, admin.organization)
    assert [w.date for w in event.weeks.all()][-1] == date(2027, 9, 28)


def test_basics_validation(client, admin):
    response = client.post("/events/new/", {**BASICS, "weeks": "21"})
    assert response.status_code == 200 and not Event.objects.exists()


def test_scoring_and_back(client, admin):
    event = make_event()
    response = client.post(f"/events/{event.pk}/setup/scoring/",
                           {"match_format": "best_of_3", "points_to_win": "15", "win_by_two": "on", "nav": "back"})
    event.refresh_from_db()
    assert response.url == f"/events/{event.pk}/setup/basics/"
    assert (event.match_format, event.points_to_win, event.setup_step) == ("best_of_3", 15, 2)


def test_stepper_goto_saves_first(client, admin):
    event = make_event()
    client.post(f"/events/{event.pk}/setup/basics/", {**BASICS, "nav": "goto:flights"})
    event.refresh_from_db()
    assert event.name == "Fall League"


def test_setup_redirects_to_first_open_step(client, admin):
    event = make_event(); event.setup_step = 2; event.save()
    assert client.get(f"/events/{event.pk}/setup/").url == f"/events/{event.pk}/setup/flights/"


def test_access(client, admin):
    other = make_event(); Event.objects.filter(pk=other.pk).update(
        organization=Organization.objects.create(name="Other"))
    cup = make_event(name="Cup", type="tournament", window_minutes=120)
    assert client.get(f"/events/{other.pk}/setup/basics/").status_code == 404
    assert client.get(f"/events/{cup.pk}/setup/basics/").status_code == 404
    assert client.get(f"/events/{cup.pk}/setup/nonsense/").status_code == 404
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=admin.organization))
    assert client.get("/events/new/").status_code == 403


def test_weeks_change_marks_stale(client, admin):
    event = make_event(weeks=1)
    flight = add_flight(event, games=(1,)); add_team(flight, "A"); add_team(flight, "B")
    generate_event(event)
    client.post(f"/events/{event.pk}/setup/basics/", {**BASICS, "weeks": "2"})
    event.refresh_from_db()
    assert event.weeks.count() == 2 and event.schedule_stale is True


def test_locked_basics_only_name_changes(client, admin):
    event = make_event(weeks=1, courts=2)
    flight = add_flight(event, games=(1,)); add_team(flight, "A"); add_team(flight, "B")
    generate_event(event); score(Match.objects.get())
    page = client.get(f"/events/{event.pk}/setup/basics/").content.decode()
    assert "Scores have been entered, so the setup is locked. Individual games can still be moved." in page
    client.post(f"/events/{event.pk}/setup/basics/", {**BASICS, "courts": "5", "weeks": "3"})
    event.refresh_from_db()
    assert (event.name, event.courts, event.weeks.count()) == ("Fall League", 2, 1)


def test_my_events_links(client, admin):
    league = make_event()
    make_event(name="Cup", type="tournament", window_minutes=120)
    html = client.get("/events/").content.decode()
    assert f'href="/events/{league.pk}/setup/"' in html
    assert "/setup/" not in html.replace(f"/events/{league.pk}/setup/", "")   # tournament row has no setup link
