import html

import pytest

from accounts.models import Organization
from league.models import Match, Player, Team
from league.scheduling import generate_event
from tests.factories import add_flight, add_player, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(client):
    event = make_event(weeks=4)
    flight = add_flight(event, games=())
    flight.games_plan = ""; flight.save()
    client.force_login(admin_of(event.organization))
    return event, flight


def post_team(client, event, flight, **fields):
    data = {"action": "save_team", "flight": flight.pk, "name": "Dinkers",
            "player1": "Sam Lee", "player1_email": "sam@example.com",
            "player2": "Pat Kim <pat@example.com>", "player2_email": ""}
    data.update(fields)
    return client.post(f"/events/{event.pk}/setup/teams/?flight={flight.pk}", data)


def test_add_team_with_new_and_existing_player(client, setup):
    event, flight = setup
    pat = add_player(event.organization, "Pat Kim", "pat@example.com")
    assert post_team(client, event, flight).status_code == 302
    team = Team.objects.get(name="Dinkers")
    assert set(team.players.values_list("name", flat=True)) == {"Sam Lee", "Pat Kim"}
    assert Player.objects.filter(name="Pat Kim").count() == 1 and team.players.filter(pk=pat.pk).exists()


@pytest.mark.parametrize("fields, message", [
    ({"name": "dinkers"}, "There's already a team called Dinkers in this flight."),
    ({"name": "Smashers", "player1": "Ann Cho <ann@example.com>", "player1_email": "",
      "player2": "Ann Cho <ann@example.com>"}, "Pick two different players."),
    ({"name": "Smashers", "player1": "Ann Cho", "player1_email": "pat@example.com"},
     "Pat Kim <pat@example.com> already uses that email. Pick them from the list."),
])
def test_team_validation(client, setup, fields, message):
    event, flight = setup
    add_player(event.organization, "Pat Kim", "pat@example.com")
    add_player(event.organization, "Ann Cho", "ann@example.com")
    post_team(client, event, flight)
    # Messages are escaped like all text; unescape so the literal "<email>" can be compared.
    assert message in html.unescape(post_team(client, event, flight, **fields).content.decode())


def test_player_already_on_team_in_flight(client, setup):
    event, flight = setup
    add_player(event.organization, "Pat Kim", "pat@example.com")
    post_team(client, event, flight)
    page = html.unescape(
        post_team(client, event, flight, name="Smashers", player1="Ann Cho", player1_email="").content.decode()
    )
    assert "Pat Kim is already on Dinkers in this flight." in page


def test_ambiguous_name(client, setup):
    event, flight = setup
    add_player(event.organization, "Sam Lee"); add_player(event.organization, "Sam Lee")
    page = post_team(client, event, flight, player1_email="").content.decode()
    assert "Two players are named Sam Lee. Pick one from the list." in page


def test_adding_teams_refreshes_auto_grid(client, setup):
    event, flight = setup
    for i in range(4):
        post_team(client, event, flight, name=f"T{i}", player1=f"P{i}a", player1_email="",
                  player2=f"P{i}b")
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 2, 1, 1]


def test_delete_team_after_generate(client, setup):
    event, flight = setup
    flight.games_plan = "custom"; flight.games_per_team_by_week = [1, 1, 1, 1]; flight.save()
    teams = [add_team(flight, n) for n in "ABC"]
    generate_event(event)
    client.post(f"/events/{event.pk}/setup/teams/{teams[0].pk}/delete/")
    event.refresh_from_db()
    assert not Team.objects.filter(pk=teams[0].pk).exists()
    assert not Match.objects.filter(flight=flight).exists() and event.schedule_stale


def test_player_search_is_org_scoped(client, setup):
    event, _ = setup
    add_player(event.organization, "Sam Lee", "sam@example.com")
    add_player(Organization.objects.create(name="Other"), "Sam Other", "so@example.com")
    page = client.get(f"/events/{event.pk}/setup/teams/players/?q=sam").content.decode()
    assert 'value="Sam Lee &lt;sam@example.com&gt;"' in page and "Sam Other" not in page


def test_amber_note_and_next_not_blocked(client, setup):
    event, flight = setup
    assert "Add at least 2 teams to Intermediate Men&#x27;s before generating." in \
        client.get(f"/events/{event.pk}/setup/teams/").content.decode()
    response = client.post(f"/events/{event.pk}/setup/teams/", {"nav": "next"})
    assert response.url == f"/events/{event.pk}/setup/games/"
    event.refresh_from_db()
    assert event.setup_step >= 4


def test_no_flights_empty_state(client):
    event = make_event()
    client.force_login(admin_of(event.organization))
    page = client.get(f"/events/{event.pk}/setup/teams/").content.decode()
    assert "Add a flight first." in page


def test_edit_team_and_name_ok_for_itself(client, setup):
    event, flight = setup
    team = add_team(flight, "Dinkers")
    player1, player2 = [m.player for m in team.members.order_by("pk")]
    response = post_team(
        client, event, flight, team=team.pk, name="dinkers",
        player1=f"{player1.name} (#{player1.pk})", player1_email="",
        player2=f"{player2.name} (#{player2.pk})",
    )
    assert response.status_code == 302
    team.refresh_from_db()
    assert team.name == "dinkers" and team.members.count() == 2


def test_player_search_blank_returns_first_ten(client, setup):
    event, _ = setup
    for i in range(12):
        add_player(event.organization, f"P{i:02d}")
    page = client.get(f"/events/{event.pk}/setup/teams/players/").content.decode()
    assert page.count("<option") == 10


def test_other_orgs_event_404(client, setup):
    other = make_event(name="X")
    other.organization = Organization.objects.create(name="Else")
    other.save()
    assert client.get(f"/events/{other.pk}/setup/teams/players/").status_code == 404
