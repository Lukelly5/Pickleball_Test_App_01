from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import Organization, User
from league.models import Event, Player, Team, Week
from league.scheduling import generate_event
from tests.factories import add_flight, add_player, add_team, make_event

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")


@pytest.fixture
def event():
    event = make_event(weeks=4, courts=3, status=Event.Status.PUBLISHED)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in NAMES:
        add_team(flight, n)
    generate_event(event)
    today = timezone.localdate()
    for week in event.weeks.all():
        Week.objects.filter(pk=week.pk).update(date=today + timedelta(days=7 * (week.number - 2)))
    event.ensure_share_token()
    return event


@pytest.fixture
def client():
    return Client()


def get(client, token, tab="schedule", query="", **extra):
    return client.get(f"/s/{token}/{tab}/{query}", **extra)


def test_share_schedule_public(client, event):
    t = event.share_token
    r = get(client, t)
    assert r.status_code == 200
    html = r.content.decode()
    assert "data-nav" not in html
    assert "/settings/" not in html
    assert f'href="/s/{t}/standings/"' in html and f'href="/s/{t}/teams/"' in html
    assert r["X-Robots-Tag"] == "noindex"


def test_share_keeps_tonight(client, event):
    t = event.share_token
    html = get(client, t).content.decode()
    assert "Tonight — Week 2 · all flights" in html
    assert f'<a href="/s/{t}/schedule/?view=tonight' in html


def test_share_pills_stay_on_share_url(client, event):
    t = event.share_token
    assert f'href="/s/{t}/schedule/?week=3' in get(client, t).content.decode()


def test_share_htmx_partial_noindex(client, event):
    r = get(client, event.share_token, HTTP_HX_REQUEST="true")
    assert r.status_code == 200
    assert "<html" not in r.content.decode()
    assert r["X-Robots-Tag"] == "noindex"


def test_share_stubs(client, event):
    for tab in ("standings", "teams"):
        r = get(client, event.share_token, tab)
        assert r.status_code == 200 and "Coming soon" in r.content.decode()
        assert r["X-Robots-Tag"] == "noindex"


def test_bad_token_404(client, event):
    assert get(client, "nope").status_code == 404


def test_draft_with_token_404(client, event):
    Event.objects.filter(pk=event.pk).update(status=Event.Status.DRAFT)
    assert get(client, event.share_token).status_code == 404


def test_reset_token_old_404(client, event):
    old = event.share_token
    new = event.reset_share_token()
    assert get(client, old).status_code == 404
    assert get(client, new).status_code == 200


def test_share_link_logged_in_other_org(client, event):
    other = Organization.objects.create(name="Other")
    user = User.objects.create_user("p@example.com", "pw", organization=other)
    Player.objects.create(organization=other, name="Dinker", email="p@example.com", user=user)
    client.force_login(user)
    r = get(client, event.share_token)
    html = r.content.decode()
    assert r.status_code == 200
    assert "data-you" not in html and "data-nav" not in html


def test_share_hides_you_chip_for_member(client, event):
    team = Team.objects.get(flight__division__event=event, name="Dinkers")
    user = User.objects.create_user("m@example.com", "pw", organization=event.organization)
    Player.objects.filter(pk=team.players.first().pk).update(user=user)
    client.force_login(user)
    assert "data-you" not in get(client, event.share_token).content.decode()


def test_completed_share_visible(client, event):
    Event.objects.filter(pk=event.pk).update(status=Event.Status.COMPLETED)
    assert get(client, event.share_token).status_code == 200


def test_share_stub_tonight_link_is_plain(client, event):
    t = event.share_token
    html = get(client, t, "standings").content.decode()
    link = f'/s/{t}/schedule/?view=tonight'
    button = html.split(f'href="{link}"')[1].split(">")[0]
    assert "hx-target" not in button


def test_share_page_hides_editor_and_score_links(client, event):
    from accounts.models import User
    from league.models import Match
    from league.score_edits import save_score

    admin = User.objects.create_user("secret-admin@example.com", "pw", organization=event.organization, is_admin=True)
    m = Match.objects.filter(flight__division__event=event, week__number=2).first()
    save_score(event, m.pk, admin, [("11", "7")], timezone.localdate())
    html = get(client, event.share_token).content.decode()
    assert "11" in html
    for leak in ("Last edited by", "secret-admin@example.com", "/matches/", "score-sheet"):
        assert leak not in html
