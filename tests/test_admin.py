import pytest

from league.models import Match
from tests.factories import add_flight, add_team, make_event

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


@pytest.mark.django_db
def test_team_member_inline_requires_two_players(admin_client):
    from league.admin import TeamMemberInline

    assert (TeamMemberInline.min_num, TeamMemberInline.max_num) == (2, 2)
    assert TeamMemberInline.validate_min and TeamMemberInline.validate_max
