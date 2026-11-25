from datetime import date

import pytest
from django.core.exceptions import PermissionDenied

from accounts.models import Organization, User
from league.models import Event, Match, Team, Week
from league.schedule_edits import GONE
from league.score_edits import (
    ScoreRefused,
    admin_locked,
    can_manage,
    can_score,
    clear_score,
    editor_name,
    save_forfeit,
    save_score,
    scorable_ids,
)
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db

TODAY = date(2027, 3, 9)
WIN_2_1 = [("11", "7"), ("9", "11"), ("11", "5")]


@pytest.fixture
def league():
    event = make_event(
        weeks=4, courts=3, status=Event.Status.PUBLISHED, match_format="best_of_3"
    )
    flight = add_flight(event)
    for name in ("Dinkers", "Smashers", "Lobsters", "Kings"):
        add_team(flight, name)
    generate_event(event)
    return event


@pytest.fixture
def admin(league):
    return admin_of(league.organization)


def fresh(match):
    return Match.objects.select_related(
        "week", "team_a", "team_b", "last_edited_by", "flight__division__event"
    ).get(pk=match.pk)


def week_match(event, number):
    pk = Match.objects.filter(flight__division__event=event, week__number=number).first().pk
    return fresh(Match(pk=pk))


@pytest.fixture
def m2(league):
    return week_match(league, 2)


def player_user(match, team=None, email="p@example.com"):
    team = team or match.team_a
    user = User.objects.create_user(email, "pw", organization=match.team_a.flight.event.organization)
    player = team.members.first().player
    player.user = user
    player.save()
    return user


@pytest.fixture
def player_on(m2):
    return lambda match=m2, **kw: player_user(match, **kw)


def entry_on(event):
    event.player_score_entry = True
    event.save()


def test_admin_can_score_any_week(league, admin):
    assert can_score(admin, week_match(league, 4), TODAY)


def test_other_org_admin_cannot(league, m2):
    other = admin_of(Organization.objects.create(name="Elsewhere"), "o@example.com")
    assert not can_score(other, m2, TODAY)
    assert not can_manage(other, m2)


def test_player_needs_entry_on(league, m2, player_on):
    user = player_on()
    assert not can_score(user, m2, TODAY)
    entry_on(league)
    assert can_score(user, fresh(m2), TODAY)


def test_player_not_on_match(league, m2):
    entry_on(league)
    outsider = next(
        t
        for t in Team.objects.filter(flight__division__event=league)
        if t.pk not in (m2.team_a_id, m2.team_b_id)
    )
    user = player_user(m2, team=outsider)
    assert not can_score(user, fresh(m2), TODAY)


def test_player_future_week(league, player_on):
    entry_on(league)
    m3 = week_match(league, 3)
    user = player_on(m3)
    assert not can_score(user, fresh(m3), TODAY)
    Week.objects.filter(pk=m3.week_id).update(date=None)
    assert can_score(user, fresh(m3), TODAY)


@pytest.mark.parametrize("what", ["week", "match", "team", "draft"])
def test_not_playable(league, admin, m2, player_on, what):
    entry_on(league)
    user = player_on()
    if what == "week":
        Week.objects.filter(pk=m2.week_id).update(status=Week.Status.CANCELLED)
    elif what == "match":
        Match.objects.filter(pk=m2.pk).update(status=Match.Status.VOID)
    elif what == "team":
        Team.objects.filter(pk=m2.team_b_id).update(withdrawn_at="2027-03-01T00:00:00Z")
    else:
        Event.objects.filter(pk=league.pk).update(status=Event.Status.DRAFT)
    m = fresh(m2)
    assert not can_score(admin, m, TODAY)
    assert not can_score(user, m, TODAY)
    assert not can_manage(admin, m)


def test_player_locked_after_admin(league, admin, m2, player_on):
    entry_on(league)
    user = player_on()
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    m = fresh(m2)
    assert admin_locked(m)
    assert not can_score(user, m, TODAY)


def test_save_writes_fields(league, admin, m2):
    m, chk = save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    games = list(m.games.values_list("game_no", "points_a", "points_b"))
    assert games == [(1, 11, 7), (2, 9, 11), (3, 11, 5)]
    assert m.winner_id == m.team_a_id and m.status == "final"
    assert m.forfeited_by_id is None and m.last_edited_by == admin


def test_admin_saves_one_nil(league, admin, m2):
    raw = [("11", "7"), ("", ""), ("", "")]
    m, chk = save_score(league, m2.pk, admin, raw, TODAY, anyway=True)
    assert m.games.count() == 1 and m.winner_id == m.team_a_id


def test_save_anyway_needs_flag(league, admin, m2):
    raw = [("11", "7"), ("", ""), ("", "")]
    m, chk = save_score(league, m2.pk, admin, raw, TODAY)
    assert m is None and chk.save_anyway
    assert m2.games.count() == 0 and fresh(m2).status == "scheduled"


def test_player_blocked_writes_nothing(league, m2, player_on):
    entry_on(league)
    user = player_on()
    m, chk = save_score(league, m2.pk, user, [("11", "10"), ("", ""), ("", "")], TODAY)
    assert m is None and not chk.can_save and m2.games.count() == 0


def test_player_can_save_valid(league, m2, player_on):
    entry_on(league)
    user = player_on()
    m, _ = save_score(league, m2.pk, user, WIN_2_1, TODAY)
    assert m.last_edited_by == user and m.games.count() == 3


def test_player_refused_after_admin(league, admin, m2, player_on):
    entry_on(league)
    user = player_on()
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    with pytest.raises(ScoreRefused, match="An admin has already scored this match."):
        save_score(league, m2.pk, user, WIN_2_1, TODAY)


def test_player_denied_otherwise(league, m2, player_on):
    user = player_on()  # entry is off
    with pytest.raises(PermissionDenied):
        save_score(league, m2.pk, user, WIN_2_1, TODAY)


def test_save_gone_match(league, admin, m2):
    pk = m2.pk
    Match.objects.filter(pk=pk).delete()
    with pytest.raises(ScoreRefused, match="no longer on the schedule") as exc:
        save_score(league, pk, admin, WIN_2_1, TODAY)
    assert str(exc.value) == GONE


def test_edit_replaces_games(league, admin, m2):
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    save_score(league, m2.pk, admin, [("11", "7"), ("11", "5"), ("", "")], TODAY)
    assert m2.games.count() == 2


def test_save_after_forfeit_clears_forfeit(league, admin, m2):
    save_forfeit(league, m2.pk, admin, m2.team_b_id)
    m, _ = save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    assert m.forfeited_by_id is None and m.games.count() == 3


def test_forfeit(league, admin, m2):
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    m = save_forfeit(league, m2.pk, admin, m2.team_b_id)
    assert m.forfeited_by_id == m2.team_b_id and m.winner_id == m2.team_a_id
    assert m.games.count() == 0 and m.status == "final" and m.last_edited_by == admin


def test_forfeit_player_denied(league, m2, player_on):
    entry_on(league)
    with pytest.raises(PermissionDenied):
        save_forfeit(league, m2.pk, player_on(), m2.team_b_id)


def test_forfeit_wrong_team(league, admin, m2):
    other = Team.objects.exclude(pk__in=(m2.team_a_id, m2.team_b_id)).first()
    with pytest.raises(ScoreRefused, match="Choose the team that forfeited."):
        save_forfeit(league, m2.pk, admin, other.pk)


def test_clear(league, admin, m2, player_on):
    entry_on(league)
    user = player_on()
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    m = clear_score(league, m2.pk, admin)
    assert m.games.count() == 0 and m.winner_id is None and m.forfeited_by_id is None
    assert m.status == "scheduled" and m.last_edited_by == admin
    assert not can_score(user, fresh(m2), TODAY)


def test_clear_player_denied(league, m2, player_on):
    entry_on(league)
    with pytest.raises(PermissionDenied):
        clear_score(league, m2.pk, player_on())


def test_clear_last_score_unlocks(league, admin, m2):
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    assert league.has_scores()
    clear_score(league, m2.pk, admin)
    assert not league.has_scores()


def test_editor_name(league, admin, m2, player_on):
    user = player_on()
    assert editor_name(user) == user.player.name
    admin.first_name, admin.last_name = "Ada", "Lee"
    assert editor_name(admin) == "Ada Lee"
    assert editor_name(User(email="x@example.com")) == "x@example.com"
    assert editor_name(None) == ""


def test_scorable_ids(league, m2, player_on):
    entry_on(league)
    user = player_on()
    team = m2.team_a_id
    all_matches = Match.objects.filter(flight__division__event=league).select_related("week")
    expected = {
        m.pk
        for m in all_matches
        if team in (m.team_a_id, m.team_b_id) and m.week.date <= TODAY
    }
    assert expected
    ids = [m.pk for m in all_matches]
    assert scorable_ids(user, league, ids, TODAY) == expected


def test_non_member_on_admin_locked_match_is_denied(league, admin, m2, player_on):
    entry_on(league)
    save_score(league, m2.pk, admin, WIN_2_1, TODAY)
    other = next(t for t in Team.objects.filter(flight__division__event=league) if t not in (m2.team_a, m2.team_b))
    user = player_user(m2, team=other, email="q@example.com")
    with pytest.raises(PermissionDenied):
        save_score(league, m2.pk, user, WIN_2_1, TODAY)
    assert not can_score(user, m2, TODAY)
