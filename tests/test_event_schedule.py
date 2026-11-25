from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Organization, User
from league.display import short_day
from league.models import Event, Match, Player, Team, TeamMember, Week
from league.scheduling import generate_event
from tests.factories import add_flight, add_player, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")


@pytest.fixture
def league(client):
    event = make_event(weeks=4, courts=3, status=Event.Status.PUBLISHED)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in NAMES:
        add_team(flight, n)
    generate_event(event)
    today = timezone.localdate()
    for week in event.weeks.all():
        Week.objects.filter(pk=week.pk).update(date=today + timedelta(days=7 * (week.number - 2)))
    client.force_login(admin_of(event.organization))
    return event


def url(event, tab="schedule", query=""):
    return f"/events/{event.pk}/{tab}/{query}"


def player_user(event, team_name="Dinkers", email="p@example.com"):
    team = Team.objects.get(flight__division__event=event, name=team_name)
    player = team.players.first()
    user = User.objects.create_user(email, "pw", organization=event.organization)
    Player.objects.filter(pk=player.pk).update(user=user)
    return user


def test_admin_sees_all_tabs(client, league):
    html = client.get(url(league)).content.decode()
    for tab in ("schedule", "standings", "teams"):
        assert f'href="/events/{league.pk}/{tab}/"' in html
    assert 'aria-current="page"' in html
    schedule_tab = html.split(f'href="/events/{league.pk}/schedule/"')[1].split(">")[0]
    assert 'aria-current="page"' in schedule_tab
    assert f'href="/events/{league.pk}/settings/"' in html
    assert ">Settings<" in html


def test_game_night_opens_tonight(client, league):
    assert "Tonight — Week 2 · all flights" in client.get(url(league)).content.decode()


def test_week_pill_and_date(client, league):
    html = client.get(url(league, query="?week=3")).content.decode()
    week3 = league.weeks.get(number=3)
    pill = html.split(">Wk3<")[0].rsplit("<a", 1)[1]
    assert 'aria-current="page"' in pill
    assert short_day(week3.date) in html


def test_player_sees_no_settings(client, league):
    client.force_login(player_user(league))
    r = client.get(url(league))
    assert r.status_code == 200
    html = r.content.decode()
    assert "/settings/" not in html
    assert ">Settings<" not in html
    cards = html.split("<article")[1:]
    assert all(("data-you" in c) == ("Dinkers" in c) for c in cards)
    assert any("Dinkers" in c for c in cards)


def test_you_chip_for_player_on_two_flights(client, league):
    org = league.organization
    shared = add_player(org, "Shared")
    # The shared player replaces one of Dinkers' two players, and also joins a mixed team.
    TeamMember.objects.filter(team__name="Dinkers").first().delete()
    TeamMember.objects.create(team=Team.objects.get(name="Dinkers"), player=shared)
    mixed = add_flight(league, "advanced", "mixed", games=(2, 2, 2, 2))
    add_team(mixed, "Mixers", players=(shared, add_player(org, "Partner")))
    for n in ("M2", "M3", "M4"):
        add_team(mixed, n)
    generate_event(league)
    user = User.objects.create_user("s@example.com", "pw", organization=org)
    Player.objects.filter(pk=shared.pk).update(user=user)
    client.force_login(user)
    html = client.get(url(league, query="?view=tonight")).content.decode()
    mine = [c for c in html.split("<article")[1:] if "data-you" in c]
    assert any("Dinkers" in c for c in mine) and any("Mixers" in c for c in mine)


def test_other_org_404(client, league):
    other = Organization.objects.create(name="Other")
    client.force_login(admin_of(other, "o@example.com"))
    assert client.get(url(league)).status_code == 404


def test_user_without_org_404(client, league):
    client.force_login(User.objects.create_user("n@example.com", "pw"))
    assert client.get(url(league)).status_code == 404


def test_anonymous_redirects_to_login(client, league):
    client.logout()
    r = client.get(url(league))
    assert r.status_code == 302 and "/login/" in r["Location"]


def test_draft_admin_redirects_to_preview(client, league):
    Event.objects.filter(pk=league.pk).update(status=Event.Status.DRAFT)
    r = client.get(url(league))
    assert r.status_code == 302 and r["Location"] == f"/events/{league.pk}/preview/"


def test_draft_player_404(client, league):
    Event.objects.filter(pk=league.pk).update(status=Event.Status.DRAFT)
    client.force_login(player_user(league))
    assert client.get(url(league)).status_code == 404


def test_htmx_partial(client, league):
    r = client.get(url(league), HTTP_HX_REQUEST="true")
    html = r.content.decode()
    assert "<html" not in html and "data-card" in html
    assert "HX-Request" in r["Vary"]


def test_history_restore_full_page(client, league):
    r = client.get(url(league), HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true")
    assert "<html" in r.content.decode()


def test_stub_tabs(client, league):
    for tab in ("standings", "teams"):
        html = client.get(url(league, tab)).content.decode()
        assert "Coming soon" in html
        link = html.split(f'href="/events/{league.pk}/{tab}/"')[1].split(">")[0]
        assert 'aria-current="page"' in link


def test_completed_event_visible(client, league):
    Event.objects.filter(pk=league.pk).update(status=Event.Status.COMPLETED)
    r = client.get(url(league))
    assert r.status_code == 200 and "Completed" in r.content.decode()


def test_no_matches_message(client, league):
    Match.objects.all().delete()
    html = client.get(url(league)).content.decode()
    assert "The schedule hasn&#x27;t been published yet." in html


def test_publish_lands_on_schedule(client, league):
    Event.objects.filter(pk=league.pk).update(status=Event.Status.DRAFT)
    r = client.post(f"/events/{league.pk}/preview/publish/", {"confirm": "1"})
    assert r["Location"] == f"/events/{league.pk}/schedule/"


def no_game_today(league):
    for week in league.weeks.all():
        Week.objects.filter(pk=week.pk).update(date=week.date + timedelta(days=1))


def test_round_headings(client, league):
    html = client.get(url(league)).content.decode()
    assert '<h3 class="mb-2 text-sm font-extrabold text-ink">Round 1</h3>' in html


def test_pills_carry_filters(client, league):
    flight = league.divisions.first().flights.first()
    html = client.get(url(league, query=f"?week=2&division=intermediate&flight={flight.pk}")).content.decode()
    href = f"{url(league)}?week=3&amp;division=intermediate&amp;flight={flight.pk}"
    assert f'href="{href}"' in html
    assert f'hx-get="{href}"' in html


def test_pills_drop_filters_in_tonight_mode(client, league):
    html = client.get(url(league, query="?view=tonight")).content.decode()
    assert f'href="{url(league)}?week=3"' in html


def test_hidden_week_input(client, league):
    html = client.get(url(league, query="?week=3")).content.decode()
    assert '<input type="hidden" name="week" value="3">' in html
    no_game_today(league)
    html = client.get(url(league, query="?view=tonight")).content.decode()
    assert 'name="week"' not in html


def test_next_game_night_link(client, league):
    no_game_today(league)
    html = client.get(url(league, query="?view=tonight")).content.decode()
    link = f"{url(league)}?week=2"
    assert f'href="{link}"' in html and f'hx-get="{link}"' in html
    assert "Next game night:" in html


def test_schedule_tab_tonight_button_swaps(client, league):
    html = client.get(url(league)).content.decode()
    link = f"{url(league)}?view=tonight"
    button = html.split(f'href="{link}"')[1].split(">")[0]
    assert f'hx-get="{link}"' in button and 'hx-target="#event-body"' in button


def test_tonight_button_on_other_tabs_is_plain_link(client, league):
    link = f"{url(league)}?view=tonight"
    for tab in ("standings", "teams", "settings"):
        html = client.get(url(league, tab)).content.decode()
        button = html.split(f'href="{link}"')[1].split(">")[0]
        assert "hx-target" not in button and "hx-get" not in button


def test_forfeit_card_shows_winner(client, league):
    match = Match.objects.filter(week__number=2).first()
    Match.objects.filter(pk=match.pk).update(
        forfeited_by=match.team_b, winner=match.team_a, status="final"
    )
    html = client.get(url(league, query="?view=tonight")).content.decode()
    assert f"Forfeit · {match.team_a.name} wins" in html
