import re

import pytest
from django.core.management import call_command
from django.test import Client

from league.models import Event

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def debug_on(settings):
    settings.DEBUG = True  # seed_demo refuses to run with DEBUG off


def test_publish_to_share_walkthrough(client):
    call_command("seed_demo", "--tonight")
    league = Event.objects.get(name="Spring Tuesday League")
    league.status = Event.Status.DRAFT
    league.share_token = None
    league.save()
    base = f"/events/{league.pk}/schedule/"

    assert client.login(username="admin@example.com", password="pickleball")
    r = client.post(f"/events/{league.pk}/preview/publish/", {"confirm": "1"}, follow=True)
    assert r.redirect_chain[-1][0] == base
    assert "Tonight — Week 2 · all flights" in r.content.decode()

    wk3 = client.get(f"{base}?week=3").content.decode()
    assert re.search(r'aria-current="page"[^>]*>Wk3', wk3)
    assert "data-card" in wk3
    advanced = client.get(f"{base}?week=3&division=advanced").content.decode()
    assert advanced.count("data-card=") > 0
    assert 'data-level="beginner"' not in advanced and 'data-level="intermediate"' not in advanced
    assert 'data-level="advanced"' in advanced
    assert "Tonight — Week 2 · all flights" in client.get(f"{base}?view=tonight").content.decode()

    settings_html = client.get(f"/events/{league.pk}/settings/").content.decode()
    share_path = re.search(r"/s/[\w-]+/", settings_html).group(0)
    share = Client().get(f"{share_path}schedule/")
    html = share.content.decode()
    assert share.status_code == 200
    assert "data-nav" not in html and "/settings/" not in html

    client.logout()
    assert client.login(username="player@example.com", password="pickleball")
    me = client.get("/me/").content.decode()
    link = re.search(rf'href="(/events/{league.pk}/schedule/\?flight=\d+)"', me).group(1)
    page = client.get(link)
    assert page.status_code == 200 and "data-you" in page.content.decode()
