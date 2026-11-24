"""Generate, review, edit and publish a league through the client, start to finish."""

import pytest

from league.models import Event, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event
from tests.test_preview_edit import (
    find_move,
    find_swap,
    find_team_swap,
    post,
    preview,
    snapshot,
    tile_for,
)

pytestmark = pytest.mark.django_db

BANNER = "This league is published, so players can see its schedule."


def test_generate_edit_publish(client):
    event = make_event(weeks=4, courts=3)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in ("Dinkers", "Smashers", "Lobsters", "Kings"):
        add_team(flight, n)
    generate_event(event)
    client.force_login(admin_of(event.organization))

    html = client.get(preview(event)).content.decode()
    assert "Draft · not visible to players" in html and "Open court" in html

    # Swap two games.
    a, b = find_swap(event)
    r = post(client, event, pick=f"g{a.pk}", target=f"g{b.pk}")
    assert r.status_code == 302
    a2, b2 = Match.objects.get(pk=a.pk), Match.objects.get(pk=b.pk)
    assert (a2.round_no, a2.court_no) == (b.round_no, b.court_no)
    assert (b2.round_no, b2.court_no) == (a.round_no, a.court_no)

    # Swap two teams.
    a, sa, b, sb = find_team_swap(event)
    ta, tb = getattr(a, f"team_{sa}_id"), getattr(b, f"team_{sb}_id")
    assert post(client, event, pick=f"t{a.pk}{sa}", target=f"t{b.pk}{sb}").status_code == 302
    a.refresh_from_db()
    b.refresh_from_db()
    assert getattr(a, f"team_{sa}_id") == tb and getattr(b, f"team_{sb}_id") == ta

    # Move a game into an open court.
    m, r_, c = find_move(event)
    assert post(client, event, pick=f"g{m.pk}", target=f"o{r_}-{c}").status_code == 302
    m.refresh_from_db()
    assert (m.round_no, m.court_no) == (r_, c)

    # A clashing swap is refused with a message and changes nothing.
    x, y = find_swap(event, ok=False)
    before = snapshot(event)
    response = post(client, event, htmx=True, pick=f"g{x.pk}", target=f"g{y.pk}")
    assert response.status_code == 200
    target = tile_for(response.content.decode(), f"g{y.pk}")
    assert "data-conflict" in target.split(">")[0]
    assert "Can&#x27;t swap:" in target or "Can't swap:" in target
    assert snapshot(event) == before

    # Publish.
    ask = client.post(f"/events/{event.pk}/preview/publish/", {})
    assert "Players will be able to see the schedule." in ask.content.decode()
    r = client.post(f"/events/{event.pk}/preview/publish/", {"confirm": "1"})
    assert r.status_code == 302
    event.refresh_from_db()
    assert event.status == Event.Status.PUBLISHED

    # My Events links the row to the preview; setup shows the published banner.
    assert f'href="/events/{event.pk}/preview/"' in client.get("/events/").content.decode()
    assert BANNER in client.get(f"/events/{event.pk}/setup/games/").content.decode()

    # A regenerate leaves a published league published.
    r = client.post(f"/events/{event.pk}/preview/regenerate/", {"confirm": "1"})
    assert r.status_code == 302
    event.refresh_from_db()
    assert event.status == Event.Status.PUBLISHED
