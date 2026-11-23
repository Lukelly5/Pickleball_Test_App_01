import pytest

from league.models import Match
from tests.factories import add_flight, add_player, add_team, make_event

MODELS = ["event", "division", "flight", "team", "player", "invite", "week", "match"]


@pytest.mark.django_db
@pytest.mark.parametrize("model", MODELS)
def test_changelist_loads(admin_client, model):
    make_event()  # so lists aren't empty
    assert admin_client.get(f"/admin/league/{model}/").status_code == 200


@pytest.mark.django_db
def test_team_page_shows_two_member_rows(admin_client):
    team = add_team(add_flight(make_event()), "Dinkers")
    page = admin_client.get(f"/admin/league/team/{team.pk}/change/")
    assert page.status_code == 200 and b"members-1-player" in page.content
    assert b"members-2-player" not in page.content


@pytest.mark.django_db
def test_user_changelist_loads(admin_client):
    assert admin_client.get("/admin/accounts/user/").status_code == 200


@pytest.mark.django_db
def test_readable_names():
    event = make_event(name="Spring League")
    flight = add_flight(event)
    a = add_team(flight, "Dinkers")
    b = add_team(flight, "Smashers")
    match = Match.objects.create(
        flight=flight, week=event.weeks.get(number=1), round_no=1, court_no=2,
        team_a=a, team_b=b,
    )
    assert str(flight) == "Intermediate Men's"
    assert str(flight.division) == "Spring League: Intermediate"
    assert str(event.weeks.get(number=1)) == "Spring League Week 1"
    assert str(match) == "Wk 1 R1 C2: Dinkers v Smashers"


@pytest.mark.django_db
def test_match_changelist_shows_readable_rows(admin_client):
    event = make_event()
    flight = add_flight(event)
    a = add_team(flight, "Dinkers")
    b = add_team(flight, "Smashers")
    Match.objects.create(
        flight=flight, week=event.weeks.get(number=1), round_no=1, court_no=1,
        team_a=a, team_b=b,
    )
    page = admin_client.get("/admin/league/match/")
    assert b"Dinkers" in page.content and b"Smashers" in page.content


def _team_post(team, rows):
    """Team change-form POST; rows is a list of (member_id or "", player_id)."""
    data = {
        "flight": team.flight_id,
        "name": team.name,
        "members-TOTAL_FORMS": len(rows),
        "members-INITIAL_FORMS": sum(1 for m, _ in rows if m),
        "members-MIN_NUM_FORMS": 2,
        "members-MAX_NUM_FORMS": 2,
    }
    for n, (member_id, player_id) in enumerate(rows):
        data[f"members-{n}-id"] = member_id
        data[f"members-{n}-team"] = team.pk
        data[f"members-{n}-player"] = player_id
    return data


@pytest.mark.django_db
def test_team_change_rejects_one_member(admin_client):
    team = add_team(add_flight(make_event()), "Dinkers")
    first = team.members.order_by("pk").first()
    data = _team_post(team, [(first.pk, first.player_id)])
    resp = admin_client.post(f"/admin/league/team/{team.pk}/change/", data)
    assert resp.status_code == 200
    assert team.members.count() == 2


@pytest.mark.django_db
def test_team_change_accepts_two_members(admin_client):
    team = add_team(add_flight(make_event()), "Dinkers")
    first, second = team.members.order_by("pk")
    new_player = add_player(team.flight.event.organization, "Newcomer")
    data = _team_post(team, [(first.pk, first.player_id), (second.pk, new_player.pk)])
    resp = admin_client.post(f"/admin/league/team/{team.pk}/change/", data)
    assert resp.status_code == 302
    assert set(team.members.values_list("player_id", flat=True)) == {
        first.player_id,
        new_player.pk,
    }
