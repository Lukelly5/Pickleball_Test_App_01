from datetime import date

import pytest
from django.utils import timezone

from league.models import Match, Week
from league.scheduling import generate_event
from league.schedule_page import Chip, ScheduleState, build_page
from tests.factories import add_flight, add_team, make_event, score

pytestmark = pytest.mark.django_db


def MAR(d):
    return date(2027, 3, d)


@pytest.fixture
def setup():
    event = make_event(weeks=4, courts=3)
    men = add_flight(event, "intermediate", "mens", games=(2, 2, 2, 2))
    men_teams = [add_team(men, f"Men {i}") for i in range(1, 6)]
    mixed = add_flight(event, "advanced", "mixed", games=(2, 2, 2, 2))
    mixed_teams = [add_team(mixed, f"Mix {i}") for i in range(1, 5)]
    generate_event(event)
    return event, men, men_teams, mixed, mixed_teams


def page(event, week=1, division="", flight=None, tonight=False, today=MAR(9), mine=frozenset()):
    return build_page(event, ScheduleState(week, division, flight, tonight), today, mine)


def cards(p):
    return [c for r in p.rounds for c in r.cards]


def men_matches(men):
    return list(Match.objects.filter(flight=men, week__number=1).order_by("round_no", "court_no"))


def card_of(p, match):
    return next(c for c in cards(p) if c.match_id == match.pk)


def test_rounds_and_courts_in_order(setup):
    p = page(setup[0])
    keys = [(c.round_no, c.court_no) for c in cards(p)]
    assert keys and keys == sorted(keys)
    assert [r.number for r in p.rounds] == sorted({k[0] for k in keys})


def test_flight_filter(setup):
    event, men = setup[:2]
    p = page(event, flight=men.pk)
    assert cards(p) and all(c.flight_name == men.name for c in cards(p))


def test_division_filter(setup):
    p = page(setup[0], division="advanced")
    assert cards(p) and all(c.level == "advanced" for c in cards(p))


def test_sit_outs_one_flight_only(setup):
    event, men, men_teams = setup[:3]
    p = page(event, flight=men.pk)
    for r in p.rounds:
        playing = {s.name for c in r.cards for s in c.sides}
        assert r.sitting_out == sorted(t.name for t in men_teams if t.name not in playing)
    assert any(r.sitting_out for r in p.rounds)
    assert all(r.sitting_out == [] for r in page(event).rounds)


def test_sit_outs_skip_withdrawn(setup):
    event, men, men_teams = setup[:3]
    gone = men_teams[0]
    gone.withdrawn_at = timezone.now()
    gone.save()
    p = page(event, flight=men.pk)
    assert all(gone.name not in r.sitting_out for r in p.rounds)
    sides = [s for c in cards(p) for s in c.sides if s.team_id == gone.pk]
    assert sides and all(s.withdrawn for s in sides)


def test_scored_card(setup):
    event, men = setup[:2]
    m = men_matches(men)[0]
    score(m, 11, 9, 1)
    score(m, 9, 11, 2)
    score(m, 11, 5, 3)
    m.status = "final"
    m.winner = m.team_a
    m.save()
    c = card_of(page(event), m)
    assert c.sides[0].chips == (Chip(11, True), Chip(9, False), Chip(11, True))
    assert c.sides[1].chips == (Chip(9, False), Chip(11, True), Chip(5, False))
    assert c.sides[0].winner and not c.sides[1].winner
    assert c.winner_name == m.team_a.name


def test_forfeit_card(setup):
    event, men = setup[:2]
    m = men_matches(men)[0]
    score(m, 11, 9, 1)
    m.forfeited_by = m.team_b
    m.winner = m.team_a
    m.status = "final"
    m.save()
    c = card_of(page(event), m)
    assert c.forfeit
    assert c.sides[0].chips == () and c.sides[1].chips == ()
    assert c.winner_name == m.team_a.name


def test_cancelled_and_void_matches_faded(setup):
    event, men = setup[:2]
    a, b = men_matches(men)[:2]
    Match.objects.filter(pk=a.pk).update(status="cancelled")
    Match.objects.filter(pk=b.pk).update(status="void")
    p = page(event)
    ca, cb = card_of(p, a), card_of(p, b)
    assert ca.faded and ca.status == "cancelled"
    assert cb.faded and cb.status == "void"


def test_cancelled_week(setup):
    event = setup[0]
    Week.objects.filter(event=event, number=2).update(status=Week.Status.CANCELLED)
    p = page(event, week=2)
    assert p.cancelled and p.rounds == []
    assert p.empty_message == "No games this week (cancelled)."


def test_mine_marks_every_team(setup):
    event, men_teams, mixed_teams = setup[0], setup[2], setup[4]
    ids = frozenset({men_teams[0].pk, mixed_teams[0].pk})
    p = page(event, mine=ids)
    sides = [s for c in cards(p) for s in c.sides]
    assert any(s.mine for s in sides)
    assert all(s.mine == (s.team_id in ids) for s in sides)


def test_tonight_with_game(setup):
    p = page(setup[0], week=2, tonight=True)
    assert p.heading == "Tonight — Week 2 · all flights"
    assert {c.level for c in cards(p)} == {"intermediate", "advanced"}
    assert all(r.sitting_out == [] for r in p.rounds)
    assert p.next_night is None


def test_tonight_no_game(setup):
    p = page(setup[0], week=None, tonight=True, today=MAR(10))
    assert p.rounds == [] and p.week_date is None
    assert p.empty_message == "No games tonight."
    assert p.next_night.number == 3
    assert len(p.pills) == 4


def test_tonight_no_later_night(setup):
    p = page(setup[0], week=None, tonight=True, today=date(2027, 6, 1))
    assert p.next_night is None


def test_no_matches_at_all(setup):
    Match.objects.all().delete()
    p = page(setup[0])
    assert not p.has_matches
    assert p.empty_message == "The schedule hasn't been published yet."


def test_filtered_empty_week(setup):
    event, men = setup[:2]
    men.games_per_team_by_week = [2, 2, 2, 0]
    men.save()
    generate_event(event)
    p = page(event, week=4, flight=men.pk)
    assert p.rounds == []
    assert p.empty_message == "No games for this flight this week."


def test_query_count_flat(setup, django_assert_max_num_queries):
    event, men = setup[:2]
    with django_assert_max_num_queries(12):
        build_page(event, ScheduleState(1, "", men.pk, False), MAR(9))


def test_card_last_edited_name_and_scored(setup, django_assert_max_num_queries):
    from tests.factories import admin_of

    event, men = setup[:2]
    m1, m2 = men_matches(men)[:2]
    user = admin_of(event.organization)
    score(m1, 11, 9, 1)
    Match.objects.filter(pk=m1.pk).update(status="final", last_edited_by=user)
    p = page(event)
    c1, c2 = card_of(p, m1), card_of(p, m2)
    assert c1.scored and c1.last_edited_name == user.email
    assert not c2.scored and c2.last_edited_name == ""
    with django_assert_max_num_queries(12):
        page(event)
