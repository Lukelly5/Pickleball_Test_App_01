import re

import pytest
from django.contrib.messages import get_messages
from django.core.management import call_command

from league.models import Event, Match

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture(autouse=True)
def debug_on(settings):
    settings.DEBUG = True  # seed_demo refuses to run with DEBUG off


def score_links(html):
    """(match pk, score URL) for every card with a score link, in page order."""
    return [(int(pk), url) for url, pk in re.findall(r'href="(/events/\d+/matches/(\d+)/score/)"', html)]


def test_score_walkthrough(client):
    call_command("seed_demo", "--tonight")
    league = Event.objects.get(name="Spring Tuesday League")
    league.match_format = "best_of_3"
    league.player_score_entry = True
    league.save()
    week2 = f"/events/{league.pk}/schedule/?week=2"

    # Admin: score the first Tonight card with the live sheet.
    assert client.login(username="admin@example.com", password="pickleball")
    tonight = client.get(f"/events/{league.pk}/schedule/?view=tonight").content.decode()
    admin_links = score_links(tonight)
    assert admin_links
    first_pk, first_url = admin_links[0]
    assert not league.has_scores()

    r = client.post(f"{first_url}check/", {"g1a": "11", "g1b": "7", "g2a": "7", "g2b": "11"}, **HX)
    assert 'id="score-g3a"' in r.content.decode()

    r = client.post(first_url, {"g1a": "11", "g1b": "7", "g2a": "9", "g2b": "11", "g3a": "11", "g3b": "5"}, **HX)
    body = r.content.decode()
    assert r.status_code == 200 and r["HX-Trigger"] == "score-saved"
    assert "hx-swap-oob" in body and f'data-card="{first_pk}"' in body
    assert "Last edited by" in body
    assert ">11<" in body and ">7<" in body and ">9<" in body

    # Setup is locked once a score exists.
    assert league.has_scores()
    before = set(Match.objects.values_list("pk", flat=True))
    r = client.post(f"/events/{league.pk}/preview/regenerate/", {"confirm": "1"})
    assert "Scores have been entered" in [str(m) for m in get_messages(r.wsgi_request)][0]
    assert set(Match.objects.values_list("pk", flat=True)) == before

    # Player: win-by-2 blocks, a legal score saves.
    client.logout()
    assert client.login(username="player@example.com", password="pickleball")
    mine = [(pk, url) for pk, url in score_links(client.get(week2).content.decode()) if pk != first_pk]
    assert mine
    player_pk, player_url = mine[0]

    r = client.post(player_url, {"g1a": "11", "g1b": "10", "g2a": "11", "g2b": "5"})
    assert "must be won by 2" in r.content.decode()
    assert Match.objects.get(pk=player_pk).status == "scheduled"

    r = client.post(player_url, {"g1a": "11", "g1b": "9", "g2a": "11", "g2b": "5"})
    assert r.status_code == 302 and r["Location"].endswith("?week=2")
    assert Match.objects.get(pk=player_pk).status == "final"

    # Admin again: edit the player's match, then the player is locked out.
    client.logout()
    assert client.login(username="admin@example.com", password="pickleball")
    r = client.post(player_url, {"g1a": "11", "g1b": "4", "g2a": "11", "g2b": "6"})
    assert r.status_code == 302
    client.logout()
    assert client.login(username="player@example.com", password="pickleball")
    r = client.post(player_url, {"g1a": "11", "g1b": "3", "g2a": "11", "g2b": "3"})
    assert "An admin has already scored this match." in r.content.decode().replace("&#x27;", "'")
    assert sorted(Match.objects.get(pk=player_pk).games.values_list("points_a", "points_b")) == [(11, 4), (11, 6)]

    # Admin: forfeit a third match, then clear it.
    client.logout()
    assert client.login(username="admin@example.com", password="pickleball")
    third_pk, third_url = next((pk, url) for pk, url in admin_links if pk not in (first_pk, player_pk))
    team = Match.objects.get(pk=third_pk).team_a_id
    assert client.post(f"{third_url}forfeit/", {"team": team}).status_code == 302
    assert Match.objects.get(pk=third_pk).forfeited_by_id == team
    client.post(f"{third_url}clear/", {"confirm": "1"})
    third = Match.objects.get(pk=third_pk)
    assert third.status == "scheduled" and third.forfeited_by_id is None and third.games.count() == 0
    html = client.get(week2).content.decode()
    card = html.split(f'data-card="{third_pk}"')[1].split("</article>")[0]
    assert "Enter score" in card
