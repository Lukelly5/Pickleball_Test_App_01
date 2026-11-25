import pytest

from accounts.models import Organization, User
from league.models import Event
from tests.factories import admin_of, make_event
from tests.test_preview_publish import toasts

pytestmark = pytest.mark.django_db


@pytest.fixture
def event(client):
    event = make_event(status=Event.Status.PUBLISHED)
    event.reset_share_token()
    client.force_login(admin_of(event.organization))
    return event


def settings_url(event):
    return f"/events/{event.pk}/settings/"


def reset_url(event):
    return f"/events/{event.pk}/settings/share/reset/"


def test_settings_shows_absolute_share_url(client, event):
    html = client.get(settings_url(event)).content.decode()
    assert f"http://testserver/s/{event.share_token}/schedule/" in html
    assert "Copy" in html
    assert "Reset link" in html
    assert f'href="/events/{event.pk}/setup/"' in html


def test_settings_creates_missing_token(client, event):
    Event.objects.filter(pk=event.pk).update(share_token=None)
    assert client.get(settings_url(event)).status_code == 200
    event.refresh_from_db()
    assert event.share_token


def test_reset_asks_first(client, event):
    old = event.share_token
    html = client.post(reset_url(event), {}).content.decode()
    assert "The old link will stop working. Reset?" in html
    assert "Keep this link" in html
    event.refresh_from_db()
    assert event.share_token == old


def test_reset_confirmed(client, event):
    old = event.share_token
    r = client.post(reset_url(event), {"confirm": "1"})
    assert r.status_code == 302
    assert r["Location"] == settings_url(event)
    assert toasts(r) == ["New share link created."]
    event.refresh_from_db()
    assert event.share_token != old
    assert client.get(f"/s/{old}/schedule/").status_code == 404
    assert client.get(f"/s/{event.share_token}/schedule/").status_code == 200


def test_settings_player_403(client, event):
    user = User.objects.create_user("p@example.com", "pw", organization=event.organization)
    client.force_login(user)
    assert client.get(settings_url(event)).status_code == 403
    assert client.post(reset_url(event), {"confirm": "1"}).status_code == 403


def test_settings_other_org_404(client, event):
    other = Organization.objects.create(name="Other Club")
    client.force_login(admin_of(other, "b@example.com"))
    assert client.get(settings_url(event)).status_code == 404
    assert client.post(reset_url(event), {"confirm": "1"}).status_code == 404


def test_settings_draft_redirects_to_preview(client, event):
    Event.objects.filter(pk=event.pk).update(status=Event.Status.DRAFT, share_token=None)
    r = client.get(settings_url(event))
    assert r.status_code == 302
    assert r["Location"] == f"/events/{event.pk}/preview/"
    r = client.post(reset_url(event), {"confirm": "1"})
    assert r.status_code == 302
    assert r["Location"] == f"/events/{event.pk}/preview/"
    event.refresh_from_db()
    assert event.share_token is None


def test_reset_requires_post(client, event):
    assert client.get(reset_url(event)).status_code == 405
