import re

import pytest

from league import schedule_edits as edits
from league.models import Event, Match
from league.preview import build_board, parse_state
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db


@pytest.fixture
def wide(client):
    """Eight teams on four courts, so round 1 fills courts 1-4."""
    event = make_event(weeks=2, courts=4)
    flight = add_flight(event, games=(3, 3))
    for i in range(8):
        add_team(flight, f"Team{i}")
    generate_event(event)
    client.force_login(admin_of(event.organization))
    return event


def lower_courts(event, n=3):
    Event.objects.filter(pk=event.pk).update(courts=n)
    event.refresh_from_db()


def round1_on(event, court):
    return Match.objects.get(
        flight__division__event=event, week__number=1, round_no=1, court_no=court
    )


def test_swap_after_courts_lowered(wide):
    event = wide
    a, b = round1_on(event, 3), round1_on(event, 4)
    lower_courts(event)
    edits.swap_games(event, a.pk, b.pk)
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.court_no, b.court_no) == (4, 3)
    assert not Match.objects.filter(flight__division__event=event, court_no__gt=4).exists()


def test_board_renders_games_on_dropped_courts(wide):
    event = wide
    lower_courts(event)
    board = build_board(event, parse_state(event, __import__("django.http").http.QueryDict("")))
    n = Match.objects.filter(flight__division__event=event, week__number=1).count()
    rendered = [t for row in board.rows for t in row if t.kind == "game"]
    assert len(rendered) == n
    assert board.courts == 4
    extra = [t for row in board.rows for t in row if t.court_no > event.courts and t.kind == "open"]
    assert all(t.actions == {} for t in extra)


def test_tab_hrefs_absolute_on_confirm_pages(client, wide):
    event = wide
    for action in ("regenerate", "publish"):
        r = client.post(f"/events/{event.pk}/preview/{action}/")
        html = r.content.decode()
        hrefs = re.findall(r'<a href="([^"]*week=2[^"]*)"', html)
        assert hrefs and all(h.startswith(f"/events/{event.pk}/preview/") for h in hrefs)
        assert client.get(hrefs[0].replace("&amp;", "&")).status_code == 200


def test_completed_event_not_draft_copy(client, wide):
    event = wide
    Event.objects.filter(pk=event.pk).update(status=Event.Status.COMPLETED)
    html = client.get(f"/events/{event.pk}/preview/").content.decode()
    assert "Draft · not visible" not in html
    assert "Completed" in html
    assert event.__class__.objects.get(pk=event.pk).is_visible


def test_fairness_even_has_sr_text(client, wide):
    html = client.get(f"/events/{wide.pk}/preview/").content.decode()
    assert 'aria-label="even"' not in html
    assert '<span class="sr-only">even</span>' in html


def test_scored_tile_label(client, wide):
    event = wide
    m = round1_on(event, 1)
    score(m)
    html = client.get(f"/events/{event.pk}/preview/").content.decode()
    assert html.count("data-scored") == 1
    tile = re.search(r'<div data-tile="game" data-key="g%d".*?(?=<div data-tile=|</td>)' % m.pk, html, re.S).group(0)
    assert "Scored" in tile
