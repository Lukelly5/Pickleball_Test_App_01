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


def test_enter_saves_the_open_team_row(client, setup):
    event, flight = setup
    url = f"/events/{event.pk}/setup/teams/?flight={flight.pk}"
    open_row = client.get(url + "&add=1").content.decode()
    first = open_row[open_row.index('<form method="post" id="step-form"'):]
    first = first[first.index("<button"):].split(">", 1)[0]
    assert 'value="save_team"' in first
    closed = client.get(url).content.decode()
    first = closed[closed.index('<form method="post" id="step-form"'):]
    assert 'value="next"' in first[first.index("<button"):].split(">", 1)[0]


HX = {"HTTP_HX_REQUEST": "true"}


def test_htmx_row_swaps_default_button_to_save(client, setup):
    event, flight = setup
    page = client.get(f"/events/{event.pk}/setup/teams/row/?flight={flight.pk}", **HX).content.decode()
    button = page[page.index('id="default-submit"'):].split(">", 1)[0]
    assert 'value="save_team"' in button and 'hx-swap-oob="true"' in button


def test_htmx_save_puts_next_back(client, setup):
    event, flight = setup
    url = f"/events/{event.pk}/setup/teams/?flight={flight.pk}"
    data = {"action": "save_team", "flight": flight.pk, "name": "Dinkers", "player1": "A One",
            "player1_email": "", "player2": "B Two", "player2_email": ""}
    page = client.post(url, data, **HX).content.decode()
    button = page[page.index('id="default-submit"'):].split(">", 1)[0]
    assert 'value="next"' in button and 'hx-swap-oob="true"' in button


def test_non_integer_team_is_not_a_500(client, setup):
    event, flight = setup
    assert post_team(client, event, flight, team="abc").status_code == 200  # form error, no team created
    assert client.get(f"/events/{event.pk}/setup/teams/row/?flight={flight.pk}&team=abc").status_code == 200


def teams_url(event, flight):
    return f"/events/{event.pk}/setup/teams/?flight={flight.pk}"


def row(**fields):
    data = {"name": "Dinkers", "player1": "Sam Lee", "player1_email": "sam@example.com",
            "player2": "Pat Kim", "player2_email": "pat@example.com"}
    data.update(fields)
    return data


def test_next_saves_a_typed_row(client, setup):
    event, flight = setup
    response = client.post(teams_url(event, flight), {**row(), "flight": flight.pk, "nav": "next"})
    assert response.status_code == 302 and response.url == f"/events/{event.pk}/setup/games/"
    assert Team.objects.filter(name="Dinkers").exists()


def test_next_with_invalid_row_stays_with_error(client, setup):
    event, flight = setup
    response = client.post(
        teams_url(event, flight), {**row(player2=""), "flight": flight.pk, "nav": "next"}
    )
    assert response.status_code == 200 and "Add both players, or leave both blank." in response.content.decode()
    assert not Team.objects.filter(name="Dinkers").exists()


def test_same_new_email_is_an_error_not_a_500(client, setup):
    event, flight = setup
    response = post_team(client, event, flight, player1="Sam Lee", player1_email="x@example.com",
                         player2="Pat Kim", player2_email="X@example.com")
    assert response.status_code == 200
    assert "Both players can&#x27;t use X@example.com." in response.content.decode()
    assert not Team.objects.exists() and not Player.objects.exists()


def test_bracket_email_is_validated(client, setup):
    event, flight = setup
    response = post_team(client, event, flight, player1="Foo <not an email>", player1_email="")
    assert response.status_code == 200
    assert "Enter a valid email address." in response.content.decode()
    assert not Player.objects.filter(email="not an email").exists()


def test_superscript_digit_team_is_not_a_500(client, setup):
    event, flight = setup
    assert client.get(f"/events/{event.pk}/setup/teams/row/?team=%C2%B2").status_code == 200


def test_long_player_name_is_an_error(client, setup):
    event, flight = setup
    response = post_team(client, event, flight, player1="x" * 121, player1_email="")
    assert response.status_code == 200
    assert "Keep names to 120 characters." in response.content.decode()
    assert not Player.objects.exists()


def test_other_orgs_event_404s_for_row_and_delete(client, setup):
    event, flight = setup
    other = make_event(name="X")
    other.organization = Organization.objects.create(name="Else")
    other.save()
    team = add_team(flight, "Dinkers")
    assert client.get(f"/events/{other.pk}/setup/teams/row/").status_code == 404
    assert client.post(f"/events/{other.pk}/setup/teams/{team.pk}/delete/").status_code == 404
    assert Team.objects.filter(pk=team.pk).exists()


BLANK_PLAYERS = {"player1": "", "player1_email": "", "player2": "", "player2_email": ""}


def test_team_with_no_players(client, setup):
    event, flight = setup
    assert post_team(client, event, flight, **BLANK_PLAYERS).status_code == 302
    team = Team.objects.get(name="Dinkers")
    assert team.members.count() == 0 and not Player.objects.exists()
    page = client.get(f"/events/{event.pk}/setup/teams/?flight={flight.pk}").content.decode()
    assert "No players named" in page


@pytest.mark.parametrize("fields", [
    {"player2": "", "player2_email": ""},
    {"player1": "", "player1_email": ""},
    {**BLANK_PLAYERS, "player1_email": "sam@example.com"},
])
def test_half_filled_players_rejected(client, setup, fields):
    event, flight = setup
    page = html.unescape(post_team(client, event, flight, **fields).content.decode())
    assert "Add both players, or leave both blank." in page
    assert not Team.objects.exists() and not Player.objects.exists()


def test_edit_team_clearing_both_players(client, setup):
    event, flight = setup
    team = add_team(flight, "Dinkers")
    assert post_team(client, event, flight, team=team.pk, **BLANK_PLAYERS).status_code == 302
    assert team.members.count() == 0


def test_teams_step_done_with_nameless_teams(setup):
    from league.setup import _flight_teams_ready
    _, flight = setup
    add_team(flight, "A", players=()); add_team(flight, "B", players=())
    assert _flight_teams_ready(flight)
    add_team(flight, "C", players=(add_player(flight.event.organization, "Solo"),))
    assert not _flight_teams_ready(flight)


def test_generate_with_nameless_teams(setup):
    _, flight = setup
    flight.games_plan = "custom"; flight.games_per_team_by_week = [1, 1, 1, 1]; flight.save()
    for n in "ABCD":
        add_team(flight, n, players=())
    generate_event(flight.event)
    assert Match.objects.filter(flight=flight).count() == 8
