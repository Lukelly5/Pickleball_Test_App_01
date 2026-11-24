import pytest
from django.http import QueryDict
from django.utils import timezone

from league.models import Match, Week
from league.preview import (
    Board,
    FairLine,
    TeamSlot,
    Tile,
    build_board,
    fairness,
    parse_state,
    resolve_click,
)
from league.scheduling import generate_event
from scheduler import pair_meet_text
from tests.factories import add_flight, add_team, make_event, score

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")


def build(teams=NAMES, courts=3, games=(2, 2, 2, 2)):
    event = make_event(weeks=4, courts=courts)
    flight = add_flight(event, games=games)
    for n in teams:
        add_team(flight, n)
    generate_event(event)
    return event, flight


def state(event, **q):
    return parse_state(event, QueryDict("&".join(f"{k}={v}" for k, v in q.items())))


def board(event, **q):
    return build_board(event, state(event, **q))


def week1(event):
    return list(
        Match.objects.filter(flight__division__event=event, week__number=1).order_by(
            "round_no", "court_no"
        )
    )


def tiles(b):
    return [t for row in b.rows for t in row]


# --- parse_state ---------------------------------------------------------


def test_parse_state_defaults():
    event, _ = build()
    assert state(event) == {"week": 1, "division": "", "flight": None, "pick": None}


@pytest.mark.parametrize("week", ["abc", "99", "0", "-1", ""])
def test_parse_state_junk_week(week):
    event, _ = build()
    assert state(event, week=week)["week"] == 1


def test_parse_state_good_values():
    event, flight = build()
    m = Match.objects.filter(week__number=3).first()
    s = state(event, week=3, division="intermediate", flight=flight.pk, pick=f"g{m.pk}")
    assert s == {"week": 3, "division": "intermediate", "flight": flight.pk, "pick": f"g{m.pk}"}
    assert state(event, week=3, pick=f"t{m.pk}b")["pick"] == f"t{m.pk}b"


@pytest.mark.parametrize("division", ["bogus", "advanced"])
def test_parse_state_junk_division(division):
    event, _ = build()
    assert state(event, division=division)["division"] == ""


@pytest.mark.parametrize("flight", ["x", "99999", ""])
def test_parse_state_junk_flight(flight):
    event, _ = build()
    assert state(event, flight=flight)["flight"] is None


def test_parse_state_flight_must_be_in_division():
    event, flight = build()
    other = add_flight(event, level="advanced")
    assert state(event, division="advanced", flight=flight.pk)["flight"] is None
    assert state(event, division="advanced", flight=other.pk)["flight"] == other.pk


def test_parse_state_junk_pick():
    event, _ = build()
    m1 = week1(event)[0]
    m2 = Match.objects.filter(week__number=2).first()
    for pick in ["zzz", "g", "g999999", "t1c", f"t{m1.pk}", f"g{m1.pk}x", f"g{m2.pk}"]:
        assert state(event, pick=pick)["pick"] is None, pick
    assert state(event, pick=f"g{m1.pk}")["pick"] == f"g{m1.pk}"
    assert state(event, week=2, pick=f"g{m2.pk}")["pick"] == f"g{m2.pk}"


# --- build_board ---------------------------------------------------------


def test_board_rows_and_open_tiles():
    event, _ = build()
    b = board(event)
    ms = week1(event)
    assert len(b.rows) == max(m.round_no for m in ms)
    assert all(len(r) == event.courts for r in b.rows)
    for i, row in enumerate(b.rows, start=1):
        assert [t.court_no for t in row] == [1, 2, 3]
        assert all(t.round_no == i for t in row)
    games = [t for t in tiles(b) if t.kind == "game"]
    assert len(games) == len(ms)
    g = games[0]
    assert g.key == f"g{g.match_id}"
    assert g.flight_name == "Intermediate Men's" and g.level == "intermediate"
    assert [s.key for s in g.teams] == [f"t{g.match_id}a", f"t{g.match_id}b"]
    assert not g.locked and not g.faded
    for t in tiles(b):
        if t.kind == "open":
            assert t.key == f"o{t.round_no}-{t.court_no}"
            assert t.teams == () and t.flight_name == "" and t.level == ""
            assert t.match_id is None


def test_board_rounds_include_cancelled_match():
    event, _ = build()
    last = week1(event)[-1]
    Match.objects.filter(pk=last.pk).update(round_no=7, court_no=1, status="cancelled")
    b = board(event)
    assert len(b.rows) == 7
    t = b.rows[6][0]
    assert t.kind == "cancelled" and t.key == f"x{last.pk}" and t.locked and t.actions == {}


def test_board_scored_and_withdrawn_are_locked():
    event, _ = build()
    ms = week1(event)
    score(ms[0])
    ms[1].team_a.withdrawn_at = timezone.now()
    ms[1].team_a.save()
    b = board(event)
    by = {t.match_id: t for t in tiles(b) if t.kind == "game"}
    assert by[ms[0].pk].locked and by[ms[0].pk].actions == {}
    w = by[ms[1].pk]
    assert w.locked and w.actions == {}
    assert w.teams[0].withdrawn is True and w.teams[1].withdrawn is False


def test_board_cancelled_week_is_read_only():
    event, _ = build()
    Week.objects.filter(event=event, number=3).update(status="cancelled")
    b = board(event, week=3)
    assert b.read_only
    assert [t.label for t in b.tabs] == ["Week 1", "Week 2", "Week 3 · Cancelled", "Week 4"]
    assert [t.cancelled for t in b.tabs] == [False, False, True, False]
    assert all(t.actions == {} for t in tiles(b))
    assert not board(event, week=1).read_only


def test_board_flight_filter_fades_others():
    event, flight = build()
    other = add_flight(event, level="advanced")
    for n in ("A1", "A2", "A3", "A4"):
        add_team(other, n)
    generate_event(event)
    b = board(event, flight=flight.pk)
    for t in tiles(b):
        if t.kind == "open":
            assert not t.faded and t.actions  # open courts stay clickable
        elif t.flight_name == "Advanced Men's":
            assert t.faded and t.actions == {}
        else:
            assert not t.faded and t.actions
    d = board(event, division="advanced")
    assert [f[1] for f in d.flights] == ["Advanced Men's"]
    assert [lv for lv, _ in d.divisions] == ["intermediate", "advanced"]
    assert len(board(event).flights) == 2


def test_board_empty_week():
    event = make_event()
    add_team(add_flight(event), "Solo")
    b = board(event)
    assert b.rows == []
    assert len(b.tabs) == 4


def test_board_actions_follow_pick():
    event, _ = build()
    g = [t for t in tiles(board(event)) if t.kind == "game"]
    a, other = g[0], g[1]
    b = board(event, pick=a.key)
    by = {t.key: t for t in tiles(b)}
    assert b.pick == a.key
    assert by[other.key].actions[other.key] == ("swap_games", other.key)
    assert by[other.key].actions[other.teams[0].key] == ("swap_games", other.key)
    assert by[a.key].actions[a.key] == ("select", None)
    assert by[a.key].actions[a.teams[0].key] == ("select", None)
    o = next(t for t in tiles(b) if t.kind == "open")
    assert o.actions == {o.key: ("move", o.key)}
    nopick = board(event)
    t0 = {t.key: t for t in tiles(nopick)}[other.key]
    assert t0.actions[other.key] == ("select", other.key)
    assert t0.actions[other.teams[1].key] == ("select", other.teams[1].key)
    o2 = next(t for t in tiles(nopick) if t.kind == "open")
    assert o2.actions == {o2.key: ("select", None)}


# --- resolve_click -------------------------------------------------------


def fake_board(pick):
    """A board whose tiles are games 5 and 7 and open court o2-3."""

    def game(mid, rnd, court):
        return Tile(
            f"g{mid}", "game", rnd, court, mid, "F", "intermediate",
            (TeamSlot(f"t{mid}a", "A", "intermediate", False),
             TeamSlot(f"t{mid}b", "B", "intermediate", False)),
            False, False, {},
        )

    open_ = Tile("o2-3", "open", 2, 3, None, "", "", (), False, False, {})
    return Board(
        None, 1, [], 3, [[game(5, 1, 1), game(7, 1, 2), open_]], False, "", None, pick, [], []
    )


@pytest.mark.parametrize(
    "pick,target,expected",
    [
        (None, "g5", ("select", "g5")),
        (None, "t5a", ("select", "t5a")),
        (None, "o2-3", ("select", None)),
        ("g5", "g7", ("swap_games", "g7")),
        ("g5", "t7b", ("swap_games", "g7")),
        ("g5", "g5", ("select", None)),
        ("g5", "t5a", ("select", None)),
        ("g5", "o2-3", ("move", "o2-3")),
        ("t5a", "t7b", ("swap_teams", "t7b")),
        ("t5a", "t5a", ("select", None)),
        ("t5a", "g7", ("select", "g7")),
        ("t5a", "o2-3", ("select", None)),
    ],
)
def test_resolve_click_table(pick, target, expected):
    assert resolve_click(fake_board(pick), target) == expected


@pytest.mark.parametrize("target", ["", "zzz", "g99", "t99a", "o0-1", "o9-9", "o1-1", "x5", "t5c"])
def test_resolve_click_ignores_targets_not_on_board(target):
    for pick in (None, "g5", "t5a"):
        assert resolve_click(fake_board(pick), target) == ("select", None)


def test_resolve_click_ignores_locked_faded_and_read_only():
    event, _ = build()
    ms = week1(event)
    score(ms[0])
    b = board(event, pick=f"g{ms[1].pk}")
    assert resolve_click(b, f"g{ms[0].pk}") == ("select", None)
    assert resolve_click(b, f"t{ms[0].pk}a") == ("select", None)
    Week.objects.filter(event=event, number=2).update(status="cancelled")
    m2 = Match.objects.filter(week__number=2).first()
    b2 = board(event, week=2)
    assert resolve_click(b2, f"g{m2.pk}") == ("select", None)


# --- fairness ------------------------------------------------------------


def lines(event, week=1, flight_ids=None):
    return {l.label: l for l in fairness(event, week, flight_ids)[0].lines}


def test_fairness_fresh_four_team_flight():
    event, _ = build()
    f = fairness(event, 1, None)
    assert len(f) == 1 and f[0].flight_name == "Intermediate Men's"
    ls = {l.label: l for l in f[0].lines}
    assert list(ls) == ["Games this week", "Season total", "Pairs meeting", "Longest sit"]
    assert ls["Games this week"] == FairLine("Games this week", "2 each", True)
    assert ls["Season total"] == FairLine("Season total", "8 each", True)
    pairs = {}
    for m in Match.objects.all():
        k = frozenset((m.team_a_id, m.team_b_id))
        pairs[k] = pairs.get(k, 0) + 1
    assert len(pairs) == 6
    assert ls["Pairs meeting"] == FairLine(
        "Pairs meeting", pair_meet_text(list(pairs.values())), True
    )
    assert ls["Longest sit"].ok and ls["Longest sit"].chip == ""


def test_fairness_five_team_bye_is_ok():
    event, _ = build(teams=("A", "B", "C", "D", "E"))
    ls = lines(event)
    assert ls["Games this week"].ok is True
    assert ls["Games this week"].text == "1–2 each"
    assert ls["Season total"].ok


def test_fairness_off_plan_games_names_teams():
    event, _ = build()
    m = week1(event)[0]
    m.delete()
    ls = lines(event)
    assert ls["Games this week"].ok is False
    assert m.team_a.name + " 1" in ls["Games this week"].text
    assert m.team_b.name + " 1" in ls["Games this week"].text


def test_fairness_longest_sit_flags_two_rounds():
    event, _ = build()
    last = week1(event)[-1]
    Match.objects.filter(pk=last.pk).update(round_no=4, court_no=1)
    sit = lines(event)["Longest sit"]
    assert sit.ok is False
    assert sit.text == "2 rounds"
    names = {last.team_a.name, last.team_b.name}
    assert sit.chip in {f"{n} · 2 rounds" for n in names}


def test_fairness_season_total_spread():
    event, _ = build()
    ms = list(Match.objects.filter(flight__division__event=event))
    c = ms[0].team_a
    doomed = [m for m in ms if c in (m.team_a, m.team_b)][:2]
    for m in doomed:
        m.delete()
    totals = {}
    for m in Match.objects.all():
        for t in (m.team_a, m.team_b):
            totals[t.name] = totals.get(t.name, 0) + 1
    lo, hi = min(totals.values()), max(totals.values())
    assert hi - lo >= 2
    line = lines(event)["Season total"]
    assert line.ok is False and line.text == f"{lo}–{hi} per team"
    lo_t = next(n for n in NAMES if totals[n] == lo)
    hi_t = next(n for n in NAMES if totals[n] == hi)
    assert line.chip == f"{lo_t} {lo} · {hi_t} {hi}"


def test_fairness_excludes_withdrawn_and_filters_flights():
    event, flight = build()
    other = add_flight(event, level="advanced")
    for n in ("A1", "A2", "A3", "A4"):
        add_team(other, n)
    generate_event(event)
    t = flight.teams.first()
    t.withdrawn_at = timezone.now()
    t.save()
    both = fairness(event, 1, None)
    assert [f.flight_name for f in both] == ["Intermediate Men's", "Advanced Men's"]
    ls = {l.label: l for l in both[0].lines}
    # three active teams are left; the withdrawn team's games are not counted
    assert t.name not in ls["Games this week"].text
    only = fairness(event, 1, {other.pk})
    assert [f.flight_name for f in only] == ["Advanced Men's"]
    assert {l.label: l for l in only[0].lines}["Games this week"].text == "2 each"
