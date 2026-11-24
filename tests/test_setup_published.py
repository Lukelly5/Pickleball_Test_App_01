import html as htmllib

import pytest

from league.models import Event, Match, Team
from league.scheduling import generate_event
from tests.factories import add_flight, add_player, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db

BANNER = (
    "This league is published, so players can see its schedule. Renames show up right away. "
    "Removing a team or flight removes its games from the schedule immediately. Other changes "
    "take effect when you regenerate, which replaces the schedule."
)
STEPS = ("basics", "flights", "teams", "games", "scoring")


@pytest.fixture
def setup(client):
    event = make_event(weeks=4, courts=2)
    flight = add_flight(event, games=(1, 1, 1, 1))
    for n in "ABCD":
        add_team(flight, n)
    generate_event(event)
    client.force_login(admin_of(event.organization))
    return event, flight


def publish(event):
    Event.objects.filter(pk=event.pk).update(status=Event.Status.PUBLISHED)
    event.refresh_from_db()


def save_team(client, event, flight, team, **fields):
    members = list(team.members.select_related("player").order_by("pk"))
    data = {"action": "save_team", "flight": flight.pk, "team": team.pk, "name": team.name,
            "player1": f"{members[0].player.name} <{members[0].player.email}>" if members[0].player.email else members[0].player.name,
            "player2": members[1].player.name}
    data.update(fields)
    return client.post(f"/events/{event.pk}/setup/teams/?flight={flight.pk}", data)


def stale(event):
    event.refresh_from_db()
    return event.schedule_stale


def test_rename_does_not_mark_stale(client, setup):
    event, flight = setup
    team = Team.objects.get(name="A")
    assert save_team(client, event, flight, team, name="Aces").status_code == 302
    assert Team.objects.filter(name="Aces").exists() and not stale(event)


def test_player_change_marks_stale(client, setup):
    event, flight = setup
    team = Team.objects.get(name="A")
    add_player(event.organization, "Newbie")
    save_team(client, event, flight, team, player2="Newbie")
    assert stale(event)


def test_new_team_marks_stale(client, setup):
    event, flight = setup
    client.post(f"/events/{event.pk}/setup/teams/?flight={flight.pk}",
                {"action": "save_team", "flight": flight.pk, "name": "E", "player1": "P1", "player2": "P2"})
    assert Team.objects.filter(name="E").exists() and stale(event)


def test_published_banner_on_every_step(client, setup):
    event, _ = setup
    for step in STEPS:
        assert BANNER not in client.get(f"/events/{event.pk}/setup/{step}/").content.decode()
    publish(event)
    for step in STEPS:
        assert BANNER in client.get(f"/events/{event.pk}/setup/{step}/").content.decode()


def test_completed_also_shows_banner(client, setup):
    event, _ = setup
    Event.objects.filter(pk=event.pk).update(status=Event.Status.COMPLETED)
    assert BANNER in client.get(f"/events/{event.pk}/setup/basics/").content.decode()


def test_generate_confirm_mentions_players(client, setup):
    event, flight = setup
    url = f"/events/{event.pk}/setup/games/generate/"
    data = {f"f{flight.pk}-plan": "custom", **{f"f{flight.pk}-w{i}": "1" for i in range(1, 5)}}
    assert "Players have already seen" not in client.post(url, data).content.decode()
    publish(event)
    assert "Players have already seen this schedule." in client.post(url, data).content.decode()


def test_published_team_delete_asks_first(client, setup):
    event, flight = setup
    publish(event)
    team = Team.objects.get(name="A")
    url = f"/events/{event.pk}/setup/teams/{team.pk}/delete/"
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == f"/events/{event.pk}/setup/teams/?flight={flight.pk}&delete={team.pk}"
    assert Team.objects.filter(pk=team.pk).exists()
    page = htmllib.unescape(client.get(response.url).content.decode())
    assert (f"Delete A? This also removes {flight.name}'s games from the published schedule. "
            "Regenerate to rebuild them.") in page
    assert 'name="confirm"' in page and 'role="alert"' in page
    client.post(url, {"confirm": "1"})
    assert not Team.objects.filter(pk=team.pk).exists()


def test_draft_team_delete_is_one_click(client, setup):
    event, _ = setup
    team = Team.objects.get(name="A")
    client.post(f"/events/{event.pk}/setup/teams/{team.pk}/delete/")
    assert not Team.objects.filter(pk=team.pk).exists()


def test_junk_delete_param_is_ignored(client, setup):
    event, flight = setup
    publish(event)
    for junk in ("x", "99999"):
        assert client.get(f"/events/{event.pk}/setup/teams/?flight={flight.pk}&delete={junk}").status_code == 200


def test_published_flight_removal_copy(client, setup):
    event, flight = setup
    add_flight(event, level="advanced", format="mixed")
    cells = {"cells": ["advanced:mixed"], "nav": "next"}
    sentence = "Its games will also disappear from the published schedule."
    assert sentence not in client.post(f"/events/{event.pk}/setup/flights/", cells).content.decode()
    publish(event)
    assert sentence in client.post(f"/events/{event.pk}/setup/flights/", cells).content.decode()
