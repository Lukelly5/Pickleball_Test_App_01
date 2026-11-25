from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Organization, User
from league.models import Event, Week
from tests.factories import admin_of, make_event

pytestmark = pytest.mark.django_db


def published(name="Spring Tuesday League", week_date=None, week=2, **fields):
    fields.setdefault("status", Event.Status.PUBLISHED)
    event = make_event(name=name, **fields)
    if week_date is not None:
        Week.objects.filter(event=event, number=week).update(date=week_date)
    return event


def today():
    return timezone.localdate()


@pytest.fixture
def admin_client(client):
    org, _ = Organization.objects.get_or_create(name="Waco Regional")
    client.force_login(admin_of(org))
    return client


def test_one_event_redirects(admin_client):
    event = published(week_date=today())
    r = admin_client.get("/tonight/")
    assert r.status_code == 302
    assert r["Location"] == f"/events/{event.pk}/schedule/?view=tonight"


def test_several_events_listed(admin_client):
    b = published("Bravo League", today())
    a = published("Alpha League", today())
    r = admin_client.get("/tonight/")
    assert r.status_code == 200
    html = r.content.decode()
    assert "Alpha League · Week 2" in html
    assert "Bravo League · Week 2" in html
    assert f'href="/events/{a.pk}/schedule/?view=tonight"' in html
    assert f'href="/events/{b.pk}/schedule/?view=tonight"' in html
    assert html.index("Alpha League") < html.index("Bravo League")


def test_none_shows_next(admin_client):
    event = published(week_date=today() + timedelta(days=3), week=3)
    html = admin_client.get("/tonight/").content.decode()
    assert "No games tonight." in html
    assert "Next game night:" in html
    assert event.name in html
    assert "Week 3" in html
    assert f'href="/events/{event.pk}/schedule/?week=3"' in html


def test_next_is_earliest_across_events(admin_client):
    published("Later League", today() + timedelta(days=5), week=1)
    published("Sooner League", today() + timedelta(days=2), week=2)
    html = admin_client.get("/tonight/").content.decode()
    assert "Next game night:" in html
    assert "Sooner League" in html
    assert "Later League" not in html


def test_none_and_no_next(admin_client):
    event = published(week_date=today() - timedelta(days=3))
    Week.objects.filter(event=event).update(date=today() - timedelta(days=3))
    html = admin_client.get("/tonight/").content.decode()
    assert "No games tonight." in html
    assert "Next game night" not in html


def test_drafts_completed_and_other_orgs_ignored(admin_client):
    published("Draft", today(), status=Event.Status.DRAFT)
    published("Done", today(), status=Event.Status.COMPLETED)
    other = Organization.objects.create(name="Other Club")
    event = Event.objects.create(
        organization=other, name="Other", start_date=today(), courts=2, status=Event.Status.PUBLISHED
    )
    event.set_week_count(2)
    Week.objects.filter(event=event, number=1).update(date=today())
    r = admin_client.get("/tonight/")
    assert r.status_code == 200
    assert "No games tonight." in r.content.decode()


def test_cancelled_week_today_ignored(admin_client):
    event = published(week_date=today())
    Week.objects.filter(event=event, number=2).update(status=Week.Status.CANCELLED)
    r = admin_client.get("/tonight/")
    assert r.status_code == 200
    assert "No games tonight." in r.content.decode()


def test_player_403(client):
    org, _ = Organization.objects.get_or_create(name="Waco Regional")
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=org))
    assert client.get("/tonight/").status_code == 403


def test_admin_nav_shows_tonight(admin_client):
    html = admin_client.get("/events/").content.decode()
    assert 'href="/tonight/"' in html
