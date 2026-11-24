import re

import pytest
from django.utils import timezone

import scheduler
from accounts.models import Organization
from league.models import Match, Team, Week
from league.scheduling import generate_event, load_schedule
from tests.factories import add_flight, add_team, admin_of, make_event, score
from tests.html_helpers import elements_with

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")
GONE = "That game is no longer on the schedule. Refresh and try again."


@pytest.fixture
def league(client):
    event = make_event(weeks=4, courts=3)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in NAMES:
        add_team(flight, n)
    generate_event(event)
    client.force_login(admin_of(event.organization))
    return event


def preview(event, **q):
    query = "&".join(f"{k}={v}" for k, v in q.items())
    return f"/events/{event.pk}/preview/" + (f"?{query}" if query else "")


def edit_url(event):
    return f"/events/{event.pk}/preview/edit/"


def week1(event):
    return list(
        Match.objects.filter(flight__division__event=event, week__number=1).order_by(
            "round_no", "court_no"
        )
    )


def slot(m):
    return (1, m.round_no, m.court_no)


def snapshot(event):
    return sorted(
        Match.objects.filter(flight__division__event=event).values_list(
            "id", "round_no", "court_no", "team_a_id", "team_b_id"
        )
    )


def accepted(fn):
    try:
        fn()
    except scheduler.SwapConflict:
        return False
    return True


def find_swap(event, ok=True):
    schedule = load_schedule(event)[0]
    ms = week1(event)
    for i, a in enumerate(ms):
        for b in ms[i + 1 :]:
            if accepted(lambda: scheduler.swap_games(schedule, slot(a), slot(b))) == ok:
                return a, b
    raise AssertionError("no such pair")


def find_team_swap(event):
    schedule = load_schedule(event)[0]
    ms = week1(event)
    for i, a in enumerate(ms):
        for b in ms[i + 1 :]:
            for sa in "ab":
                for sb in "ab":
                    if accepted(
                        lambda: scheduler.swap_teams(schedule, (slot(a), sa), (slot(b), sb))
                    ):
                        return a, sa, b, sb
    raise AssertionError("no team swap")


def open_slots(event):
    taken = {(m.round_no, m.court_no) for m in week1(event)}
    top = max(r for r, _ in taken)
    return [
        (r, c)
        for r in range(1, top + 1)
        for c in range(1, event.courts + 1)
        if (r, c) not in taken
    ]


def find_move(event):
    schedule = load_schedule(event)[0]
    for m in week1(event):
        for r, c in open_slots(event):
            if accepted(lambda: scheduler.move_game(schedule, slot(m), (1, r, c))):
                return m, r, c
    raise AssertionError("no move")


def tiles(html, kind=None):
    found = elements_with(html, "data-tile")
    return [t for t in found if kind is None or f'data-tile="{kind}"' in t.split(">")[0]]


def tile_for(html, key):
    return next(t for t in tiles(html) if f'data-key="{key}"' in t.split(">")[0])


# --- clickable tiles ---------------------------------------------------------


def test_select_links(client, league):
    html = client.get(preview(league)).content.decode()
    games = tiles(html, "game")
    assert games
    for tile in games:
        key = re.search(r'data-key="(g\d+)"', tile).group(1)
        assert f"pick={key}" in tile
        assert "<form" not in tile
        for side in "ab":
            assert f"pick=t{key[1:]}{side}" in tile
    for tile in tiles(html, "open"):
        assert "href=" not in tile and "<form" not in tile


def test_picked_tile_marked(client, league):
    a, b = week1(league)[:2]
    html = client.get(preview(league, pick=f"g{a.pk}")).content.decode()
    picked = tile_for(html, f"g{a.pk}")
    assert "data-selected" in picked.split(">")[0]
    # Clicking the picked tile again drops the pick.
    assert f"pick=g{a.pk}" not in picked
    assert "href=" in picked
    other = tile_for(html, f"g{b.pk}")
    assert "data-selected" not in other.split(">")[0]
    assert '<form method="post" action="/events/%d/preview/edit/"' % league.pk in other
    assert 'name="pick" value="g%d"' % a.pk in other
    assert 'name="target" value="g%d"' % b.pk in other
    for tile in tiles(html, "open"):
        assert '<form method="post" action="/events/%d/preview/edit/"' % league.pk in tile
        assert 'name="target" value="o' in tile
    # The write forms carry the page state.
    for name in ("week", "division", "flight"):
        assert f'name="{name}"' in other


def test_locked_tiles_not_clickable(client, league):
    a, b, c = week1(league)[:3]
    score(a)
    Team.objects.filter(pk=b.team_a_id).update(withdrawn_at=timezone.now())
    c.status = Match.Status.CANCELLED
    c.save()
    keys = [f"g{a.pk}", f"g{b.pk}", f"x{c.pk}"]
    d = next(m for m in week1(league) if m.pk not in (a.pk, b.pk, c.pk))
    for q in ({}, {"pick": f"g{d.pk}"}):
        html = client.get(preview(league, **q)).content.decode()
        for key in keys:
            tile = tile_for(html, key)
            assert "href=" not in tile and "<form" not in tile


# --- acting --------------------------------------------------------------------


def post(client, event, htmx=False, **data):
    data.setdefault("week", 1)
    extra = {"HTTP_HX_REQUEST": "true"} if htmx else {}
    return client.post(edit_url(event), data, **extra)


def assert_htmx_success(response):
    assert response.status_code == 200
    html = response.content.decode()
    assert "<html" not in html and "Round 1" in html
    assert "pick=" not in response["HX-Push-Url"]
    assert "week=1" in response["HX-Push-Url"]


def test_swap_games_post(client, league):
    a, b = find_swap(league)
    response = post(client, league, pick=f"g{a.pk}", target=f"g{b.pk}", division="", flight="")
    assert response.status_code == 302
    assert response["Location"] == "/events/%d/preview/?week=1" % league.pk
    a2, b2 = Match.objects.get(pk=a.pk), Match.objects.get(pk=b.pk)
    assert (a2.round_no, a2.court_no) == (b.round_no, b.court_no)
    assert (b2.round_no, b2.court_no) == (a.round_no, a.court_no)


def test_swap_games_post_htmx_and_filters_kept(client, league):
    a, b = find_swap(league)
    flight = a.flight_id
    response = post(
        client, league, htmx=True, pick=f"g{a.pk}", target=f"g{b.pk}", division="intermediate",
        flight=flight,
    )
    assert_htmx_success(response)
    assert f"flight={flight}" in response["HX-Push-Url"]
    assert "division=intermediate" in response["HX-Push-Url"]
    nojs = post(
        client, league, pick=f"g{b.pk}", target=f"g{a.pk}", division="intermediate", flight=flight
    )
    assert f"flight={flight}" in nojs["Location"] and "pick" not in nojs["Location"]


def test_move_post(client, league):
    m, r, c = find_move(league)
    response = post(client, league, pick=f"g{m.pk}", target=f"o{r}-{c}")
    assert response.status_code == 302 and "pick" not in response["Location"]
    m.refresh_from_db()
    assert (m.round_no, m.court_no) == (r, c)

    m2, r2, c2 = find_move(league)
    response = post(client, league, htmx=True, pick=f"g{m2.pk}", target=f"o{r2}-{c2}")
    assert_htmx_success(response)
    m2.refresh_from_db()
    assert (m2.round_no, m2.court_no) == (r2, c2)


def test_swap_teams_post(client, league):
    a, sa, b, sb = find_team_swap(league)
    ta, tb = getattr(a, f"team_{sa}_id"), getattr(b, f"team_{sb}_id")
    response = post(client, league, pick=f"t{a.pk}{sa}", target=f"t{b.pk}{sb}")
    assert response.status_code == 302 and "pick" not in response["Location"]
    a.refresh_from_db()
    b.refresh_from_db()
    assert getattr(a, f"team_{sa}_id") == tb and getattr(b, f"team_{sb}_id") == ta

    a, sa, b, sb = find_team_swap(league)
    response = post(client, league, htmx=True, pick=f"t{a.pk}{sa}", target=f"t{b.pk}{sb}")
    assert_htmx_success(response)


def test_select_via_post(client, league):
    a = week1(league)[0]
    response = post(client, league, pick="", target=f"g{a.pk}")
    assert response.status_code == 302 and f"pick=g{a.pk}" in response["Location"]


def test_unclickable_target_just_rerenders(client, league):
    before = snapshot(league)
    for target in ("zzz", "g999999", "t1c", "o99-99", ""):
        response = post(client, league, target=target)
        assert response.status_code == 302 and "pick" not in response["Location"]
        response = post(client, league, htmx=True, target=target)
        assert response.status_code == 200
    assert snapshot(league) == before


# --- conflicts -----------------------------------------------------------------


def test_conflict_renders_on_target(client, league):
    a, b = find_swap(league, ok=False)
    before = snapshot(league)
    response = post(client, league, htmx=True, pick=f"g{a.pk}", target=f"g{b.pk}")
    assert response.status_code == 200
    html = response.content.decode()
    target = tile_for(html, f"g{b.pk}")
    assert "data-conflict" in target.split(">")[0]
    assert "Can&#x27;t swap:" in target or "Can't swap:" in target
    assert not elements_with(html, "data-selected")
    assert snapshot(league) == before
    full = post(client, league, pick=f"g{a.pk}", target=f"g{b.pk}")
    assert full.status_code == 200 and "<html" in full.content.decode()


def test_stale_pick(client, league):
    a = week1(league)[0]
    before = snapshot(league)
    for pick in ("g999999", "t999999a"):
        response = post(client, league, htmx=True, pick=pick, target=f"g{a.pk}")
        assert response.status_code == 200
        assert GONE in response.content.decode()
    assert snapshot(league) == before


def test_direct_posts_change_nothing(client, league):
    a, b = week1(league)[:2]
    score(a)
    before = snapshot(league)
    # A scored game is not clickable, so the board never acts on it.
    for pick, target in ((f"g{a.pk}", f"g{b.pk}"), (f"g{b.pk}", f"g{a.pk}")):
        response = post(client, league, htmx=True, pick=pick, target=target)
        assert response.status_code == 200
    Week.objects.filter(number=1).update(status=Week.Status.CANCELLED)
    response = post(client, league, htmx=True, pick=f"g{b.pk}", target="o1-1")
    assert response.status_code == 200
    assert snapshot(league) == before


# --- access --------------------------------------------------------------------


def test_access(client, league):
    a, b = find_swap(league)
    assert client.get(edit_url(league)).status_code == 405
    client.logout()
    assert post(client, league, pick=f"g{a.pk}", target=f"g{b.pk}").status_code == 302
    other = Organization.objects.create(name="Other")
    client.force_login(admin_of(other, "o@example.com"))
    before = snapshot(league)
    assert post(client, league, pick=f"g{a.pk}", target=f"g{b.pk}").status_code == 404
    assert snapshot(league) == before


def test_conflict_shows_on_open_court_and_team_targets(client, league):
    schedule = load_schedule(league)[0]
    clash = next(
        (m, r, c)
        for m in week1(league)
        for r, c in open_slots(league)
        if not accepted(lambda: scheduler.move_game(schedule, slot(m), (1, r, c)))
    )
    m, r, c = clash
    html = post(client, league, htmx=True, pick=f"g{m.pk}", target=f"o{r}-{c}").content.decode()
    tile = tile_for(html, f"o{r}-{c}")
    assert "data-conflict" in tile.split(">")[0] and "Can" in tile and "move" in tile
