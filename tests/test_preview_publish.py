import re

import pytest
from django.contrib.messages import get_messages
from django.test import Client

from accounts.models import Organization, User
from league.models import Event, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")
ASK_REGEN = "Regenerate the schedule? This replaces every game, including your swaps and moves."
STALE = "Regenerate first: inputs changed since this schedule was made."


@pytest.fixture
def league(client):
    event = make_event(weeks=4, courts=3)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in NAMES:
        add_team(flight, n)
    generate_event(event)
    client.force_login(admin_of(event.organization))
    return event


def regen(event):
    return f"/events/{event.pk}/preview/regenerate/"


def pub(event):
    return f"/events/{event.pk}/preview/publish/"


def toasts(response):
    return [str(m) for m in get_messages(response.wsgi_request)]


def ids():
    return set(Match.objects.values_list("pk", flat=True))


def test_regenerate_asks_first(client, league):
    before = ids()
    r = client.post(regen(league))
    assert r.status_code == 200
    html = r.content.decode()
    assert ASK_REGEN in html and 'role="alert"' in html
    assert 'name="confirm" value="1"' in html
    assert "Players have already seen this schedule." not in html
    assert ids() == before


def test_regenerate_asks_first_published(client, league):
    Event.objects.filter(pk=league.pk).update(status=Event.Status.PUBLISHED)
    html = client.post(regen(league)).content.decode()
    assert "Players have already seen this schedule." in html


def test_regenerate_confirmed(client, league):
    Event.objects.filter(pk=league.pk).update(schedule_stale=True)
    before = ids()
    n = len(before)
    r = client.post(regen(league), {"confirm": "1"})
    assert r.status_code == 302 and r["Location"].startswith(f"/events/{league.pk}/preview/")
    assert toasts(r) == [f"Schedule regenerated · {n} games over 4 weeks"]
    assert ids().isdisjoint(before)
    league.refresh_from_db()
    assert league.schedule_stale is False


def test_regenerate_keeps_filters(client, league):
    r = client.post(regen(league) + "?week=3", {"confirm": "1"})
    assert "week=3" in r["Location"]


def test_regenerate_singular_wording():
    from league.preview_views import regenerated_message

    assert regenerated_message(1, 1) == "Schedule regenerated · 1 game over 1 week"


def test_regenerate_blocked_scored(client, league):
    score(Match.objects.first())
    before = ids()
    r = client.post(regen(league), {"confirm": "1"})
    assert r.status_code == 302
    assert "Scores have been entered" in toasts(r)[0]
    assert ids() == before


def test_regenerate_blocker(client, league):
    import league.preview_views as pv

    def boom(event):
        from scheduler import ScheduleError

        raise ScheduleError("Blocker text.")

    orig = pv.regenerate
    pv.regenerate = boom
    try:
        r = client.post(regen(league), {"confirm": "1"})
    finally:
        pv.regenerate = orig
    assert toasts(r) == ["Blocker text."]


def test_publish_asks_first(client, league):
    html = client.post(pub(league), {}).content.decode()
    assert "Publish Spring Tuesday League? Players will be able to see the schedule." in html
    assert 'name="confirm" value="1"' in html
    league.refresh_from_db()
    assert league.status == Event.Status.DRAFT


def test_publish_confirmed(client, league):
    r = client.post(pub(league), {"confirm": "1"})
    assert r.status_code == 302 and r["Location"] == "/events/"
    assert toasts(r) == ["Spring Tuesday League published"]
    league.refresh_from_db()
    assert league.status == Event.Status.PUBLISHED


def test_publish_disabled_when_stale(client, league):
    Event.objects.filter(pk=league.pk).update(schedule_stale=True)
    html = client.get(f"/events/{league.pk}/preview/").content.decode()
    assert STALE in html
    button = re.search(r"<button[^>]*>\s*Publish\s*</button>", html)
    assert button and "disabled" in button.group(0)
    r = client.post(pub(league), {"confirm": "1"})
    assert toasts(r) == [STALE]
    league.refresh_from_db()
    assert league.status == Event.Status.DRAFT


def test_publish_no_matches(client, league):
    Match.objects.all().delete()
    r = client.post(pub(league), {"confirm": "1"})
    assert toasts(r) == ["Generate a schedule before publishing."]


def test_buttons_on_page(client, league):
    url = f"/events/{league.pk}/preview/"
    html = client.get(url).content.decode()
    assert re.search(r"<button[^>]*>\s*Publish\s*</button>", html)
    assert re.search(r"<button[^>]*>\s*Regenerate\s*</button>", html)
    Event.objects.filter(pk=league.pk).update(status=Event.Status.PUBLISHED)
    html = client.get(url).content.decode()
    assert not re.search(r"<button[^>]*>\s*Publish\s*</button>", html)


def test_stale_banner_has_regenerate_button(client, league):
    Event.objects.filter(pk=league.pk).update(schedule_stale=True)
    html = client.get(f"/events/{league.pk}/preview/").content.decode()
    banner = html[html.index("Inputs changed"):]
    assert regen(league) in banner[:600]


@pytest.mark.parametrize("which", [regen, pub])
def test_access(client, league, which):
    other = Organization.objects.create(name="Other")
    client.force_login(admin_of(other, "o@example.com"))
    assert client.post(which(league), {"confirm": "1"}).status_code == 404
    player = User.objects.create_user("p@example.com", "pw", organization=league.organization)
    client.force_login(player)
    assert client.post(which(league), {"confirm": "1"}).status_code == 403


def test_csrf_confirm_form_roundtrip(league):
    c = Client(enforce_csrf_checks=True)
    c.force_login(User.objects.filter(organization=league.organization).first())
    page = c.get(f"/events/{league.pk}/preview/").content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page).group(1)
    ask = c.post(regen(league), {"csrfmiddlewaretoken": token})
    assert ask.status_code == 200
    html = ask.content.decode()
    assert ASK_REGEN in html
    token2 = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
    ok = c.post(regen(league), {"csrfmiddlewaretoken": token2, "confirm": "1"})
    assert ok.status_code == 302
