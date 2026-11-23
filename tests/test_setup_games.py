import pytest

from accounts.models import Organization
from league.models import Flight, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(client):
    event = make_event(weeks=4, courts=2)
    flight = add_flight(event, games=(1, 1, 1, 1))
    for n in "ABCD":
        add_team(flight, n)
    client.force_login(admin_of(event.organization))
    return event, flight


def grid(flight, plan="custom", weeks=("1", "1", "1", "1")):
    data = {f"f{flight.pk}-plan": plan}
    data.update({f"f{flight.pk}-w{i}": v for i, v in enumerate(weeks, start=1)})
    return data


def test_page_shows_summary(client, setup):
    event, flight = setup
    html = client.get(f"/events/{event.pk}/setup/games/").content.decode()
    assert "Each team plays every other team:" in html
    assert "8 games · 4 per team · every pair meets 1–2 times" in html
    assert "Generate schedule" in html


def test_save_custom(client, setup):
    event, flight = setup
    client.post(f"/events/{event.pk}/setup/games/", {**grid(flight, weeks=("2", "2", "1", "1")), "nav": "stay"})
    flight.refresh_from_db(); event.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 2, 1, 1] and flight.games_plan == "custom" and event.setup_step == 5


def test_preview_does_not_save(client, setup):
    event, flight = setup
    html = client.post(f"/events/{event.pk}/setup/games/preview/", grid(flight, plan="twice"),
                       HTTP_HX_REQUEST="true").content.decode()
    assert "12 games · 6 per team · every pair meets twice" in html and "<html" not in html
    flight.refresh_from_db()
    assert flight.games_plan == "custom"


@pytest.mark.parametrize("bad", ["", "-1", "x", "21"])
def test_bad_numbers(client, setup, bad):
    event, flight = setup
    for path in ("", "preview/"):
        response = client.post(f"/events/{event.pk}/setup/games/{path}",
                               {**grid(flight, weeks=(bad, "1", "1", "1")), "nav": "stay"})
        assert response.status_code == 200 and "text-danger" in response.content.decode()
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [1, 1, 1, 1]


def test_generate_goes_to_my_events_with_toast(client, setup):
    event, flight = setup
    response = client.post(f"/events/{event.pk}/setup/games/generate/", grid(flight), follow=True)
    assert response.redirect_chain[-1][0] == "/events/"
    assert "Schedule drafted · 8 games over 4 weeks" in response.content.decode()
    assert Match.objects.filter(flight=flight).count() == 8


@pytest.mark.urls("tests.future_urls")
def test_generate_goes_to_preview_when_it_exists(client, setup):
    event, flight = setup
    assert client.post(f"/events/{event.pk}/setup/games/generate/", grid(flight)).url == f"/events/{event.pk}/preview/"


def test_generate_blocked_by_preset(client, setup):
    event, flight = setup
    html = client.post(f"/events/{event.pk}/setup/games/generate/", grid(flight, plan="once")).content.decode()
    assert "Week 4 has no games — reduce weeks or choose twice." in html
    assert not Match.objects.exists()


def test_regenerate_needs_confirm_and_clears_stale(client, setup):
    event, flight = setup
    generate_event(event)
    Flight.objects.filter(pk=flight.pk).update(games_per_team_by_week=[1, 1, 1, 1])
    event.schedule_stale = True; event.save()
    url = f"/events/{event.pk}/setup/games/generate/"
    html = client.get(f"/events/{event.pk}/setup/games/").content.decode()
    assert "You changed the setup since the schedule was made. Regenerate to apply it." in html
    assert "Regenerate schedule" in html
    assert "Regenerating replaces the current draft schedule." in client.post(url, grid(flight)).content.decode()
    client.post(url, {**grid(flight, weeks=("2", "2", "1", "1")), "confirm": "1"})
    event.refresh_from_db()
    assert not event.schedule_stale and Match.objects.filter(flight=flight).count() == 12


def test_locked_hides_generate(client, setup):
    event, flight = setup
    generate_event(event); score(Match.objects.first())
    html = client.get(f"/events/{event.pk}/setup/games/").content.decode()
    assert "Generate schedule" not in html and "Regenerate schedule" not in html
    response = client.post(f"/events/{event.pk}/setup/games/generate/", {**grid(flight), "confirm": "1"}, follow=True)
    assert "Scores have been entered, so the setup is locked." in response.content.decode()


def test_generate_get_is_405(client, setup):
    event, _ = setup
    assert client.get(f"/events/{event.pk}/setup/games/generate/").status_code == 405


def test_other_org_gets_404(client, setup):
    event, flight = setup
    client.force_login(admin_of(Organization.objects.create(name="Else"), email="b@example.com"))
    for path in ("generate/", "preview/", ""):
        assert client.post(f"/events/{event.pk}/setup/games/{path}", grid(flight)).status_code == 404


def test_locked_step_post_is_refused_but_back_navigates(client, setup):
    event, flight = setup
    generate_event(event); score(Match.objects.first())
    url = f"/events/{event.pk}/setup/games/"
    assert client.post(url, {**grid(flight, weeks=("3", "3", "3", "3")), "nav": "stay"}).status_code == 302
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [1, 1, 1, 1]
    assert client.post(url, {"nav": "back"}).url.endswith("/setup/teams/")
    html = client.post(url + "preview/", grid(flight)).content.decode()
    assert "<input" not in html
