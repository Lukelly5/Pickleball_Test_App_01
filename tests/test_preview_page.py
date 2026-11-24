import pytest
from django.utils.html import escape

from accounts.models import Organization, User
from league.models import Event, Flight, Match, Week
from league.scheduling import generate_event
from tests.html_helpers import elements_with
from tests.factories import add_flight, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")


@pytest.fixture
def league(client):
    event = make_event(weeks=4, courts=3)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in NAMES:
        add_team(flight, n)
    generate_event(event)
    client.force_login(admin_of(event.organization))
    return event, flight


def url(event, **q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    return f"/events/{event.pk}/preview/" + (f"?{query}" if query else "")


def test_access(client, league):
    event, _ = league
    assert client.get(url(event)).status_code == 200
    client.logout()
    assert client.get(url(event)).status_code == 302
    player = User.objects.create_user("p@example.com", "pw", organization=event.organization)
    client.force_login(player)
    assert client.get(url(event)).status_code == 403
    other = Organization.objects.create(name="Other")
    client.force_login(admin_of(other, "o@example.com"))
    assert client.get(url(event)).status_code == 404


def test_page_shows_week_grid(client, league):
    event, _ = league
    html = client.get(url(event)).content.decode()
    assert "Draft · not visible to players" in html
    for text in ("Week 1", "Week 2", "Week 3", "Week 4", "Round 1", "Court 1", *NAMES):
        assert text in html
    assert 'data-level="intermediate"' in html
    assert "<title>" in html and "Schedule Preview · Stryde" in html


def test_open_court_and_cancelled_tiles(client, league):
    event, _ = league
    html = client.get(url(event)).content.decode()
    assert "Open court" in html
    match = Match.objects.filter(week__number=1).first()
    match.status = Match.Status.CANCELLED
    match.save()
    html = client.get(url(event)).content.decode()
    assert "Cancelled" in html


def test_filters_fade_other_flights(client, league):
    event, flight = league
    other = add_flight(event, level="advanced", games=(2, 2, 2, 2))
    for n in ("Aces", "Bolts", "Cobras", "Drivers"):
        add_team(other, n)
    generate_event(event)
    html = client.get(url(event, flight=flight.pk)).content.decode()
    faded = [t for t in elements_with(html, "data-tile") if "data-faded" in t.split(">")[0]]
    assert faded
    for tile in faded:
        assert "href=" not in tile and "<form" not in tile
    assert elements_with(html, "data-faded") == faded
    assert "Aces" in html  # faded tiles still show
    fairness = html.split('id="fairness"')[1]
    assert escape(flight.name) in fairness and escape(other.name) not in fairness


def test_division_narrows_flight_select(client, league):
    event, flight = league
    other = add_flight(event, level="advanced", games=(2, 2, 2, 2))
    for n in ("Aces", "Bolts", "Cobras", "Drivers"):
        add_team(other, n)
    generate_event(event)
    html = client.get(url(event, division="advanced")).content.decode()
    select = html.split('name="flight"')[1].split("</select>")[0]
    assert escape(other.name) in select and escape(flight.name) not in select


@pytest.mark.parametrize(
    "q", ["week=abc", "week=99", "division=bogus", "flight=x", "pick=zzz", "week=", "pick=g999999"]
)
def test_junk_params_render(client, league, q):
    event, _ = league
    response = client.get(f"/events/{event.pk}/preview/?{q}")
    assert response.status_code == 200
    assert response.context["board"].week == 1


def test_empty_state(client):
    event = make_event()
    add_flight(event)
    client.force_login(admin_of(event.organization))
    html = client.get(url(event)).content.decode()
    assert "No schedule yet" in html
    assert f"/events/{event.pk}/setup/games/" in html


def test_stale_banner(client, league):
    event, _ = league
    event.schedule_stale = True
    event.save()
    assert "Inputs changed — regenerate to apply them." in client.get(url(event)).content.decode()


def test_published_badge(client, league):
    event, _ = league
    event.status = Event.Status.PUBLISHED
    event.save()
    html = client.get(url(event)).content.decode()
    assert "Published" in html and "Draft · not visible" not in html
    assert ">Publish<" not in html


def test_no_games_this_week_and_htmx_partial(client, league):
    event, _ = league
    week = event.weeks.get(number=2)
    week.status = Week.Status.CANCELLED
    week.save()
    Match.objects.filter(week=week).delete()
    full = client.get(url(event, week=2)).content.decode()
    assert "No games this week" in full and "Week 2 · Cancelled" in full
    part = client.get(url(event, week=2), HTTP_HX_REQUEST="true").content.decode()
    assert "<html" not in part and "No games this week" in part


def test_conflict_message_on_tile(client, league, rf):
    from league.preview import build_board, parse_state
    from league.preview_views import render_preview

    event, _ = league
    request = rf.get(url(event))
    request.user = User.objects.filter(is_admin=True).first()
    state = parse_state(event, request.GET)
    board = build_board(event, state)
    key = next(t.key for row in board.rows for t in row if t.kind == "game")
    response = render_preview(request, event, state, conflict={"key": key, "message": "Can't swap: nope"}, status=200)
    html = response.content.decode()
    assert response.status_code == 200
    assert "data-conflict" in html and "Can&#x27;t swap: nope" in html


def test_row_link(client, league):
    event, _ = league
    event.status = Event.Status.PUBLISHED
    event.save()
    html = client.get("/events/").content.decode()
    assert f'href="/events/{event.pk}/preview/"' in html


def test_history_restore_gets_full_page_and_vary(client, league):
    event, _ = league
    partial = client.get(url(event), HTTP_HX_REQUEST="true")
    assert "<html" not in partial.content.decode()
    restore = client.get(url(event), HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true")
    assert "<html" in restore.content.decode()
    for response in (partial, restore, client.get(url(event))):
        assert "HX-Request" in response["Vary"]


def test_elements_with_captures_nested_markup():
    html = '<div data-tile="a"><div><a href="/x">t</a></div><input name="q"></div><p>no</p>'
    assert elements_with(html, "data-tile") == ['<div data-tile="a"><div><a href="/x">t</a></div><input name="q"></div>']
