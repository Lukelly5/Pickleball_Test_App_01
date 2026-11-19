from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import RestrictedError
from django.utils import timezone

from accounts.models import Organization
from league.models import Event, Flight, Invite, Match, Player, Team, TeamMember
from tests.factories import add_flight, add_player, add_team, make_event

pytestmark = pytest.mark.django_db


def make_match(flight, a, b, event=None, round_no=1, court_no=1, **fields):
    week = (event or flight.event).weeks.get(number=1)
    return Match(
        flight=flight, week=week, round_no=round_no, court_no=court_no,
        team_a=a, team_b=b, **fields,
    )


def test_flight_name_combines_level_and_format():
    assert add_flight(make_event()).name == "Intermediate Men's"


def test_set_week_count_adds_and_removes_weeks():
    event = make_event(weeks=4)
    assert [(w.number, w.date) for w in event.weeks.all()][:2] == [
        (1, date(2027, 3, 2)),
        (2, date(2027, 3, 9)),
    ]
    event.set_week_count(2)
    assert list(event.weeks.values_list("number", flat=True)) == [1, 2]


def test_event_defaults_match_prd_a3():
    e = make_event()
    assert (
        e.status, e.match_format, e.points_to_win, e.win_by_two,
        e.player_score_entry, e.share_token,
    ) == ("draft", "single", 11, True, False, None)


def test_tournament_needs_window_and_defaults_game_length():
    e = make_event(type="tournament", weeks=1)
    with pytest.raises(ValidationError):
        e.full_clean()
    e.window_minutes = 120
    e.full_clean()
    assert e.game_minutes == 15


def test_games_per_team_must_be_non_negative_ints():
    f = add_flight(make_event(), games=[2, -1])
    with pytest.raises(ValidationError):
        f.full_clean()


def test_team_cannot_have_a_third_member():
    team = add_team(add_flight(make_event()), "Dinkers")
    extra = TeamMember(team=team, player=add_player(team.flight.event.organization, "Sam"))
    with pytest.raises(ValidationError):
        extra.full_clean()


def test_team_member_must_belong_to_events_organization():
    flight = add_flight(make_event())
    team = Team.objects.create(flight=flight, name="Solo")
    other = Organization.objects.create(name="Elsewhere")
    member = TeamMember(team=team, player=add_player(other, "Outsider"))
    with pytest.raises(ValidationError):
        member.full_clean()


def test_match_teams_must_differ():
    flight = add_flight(make_event())
    a = add_team(flight, "A")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_match(flight, a, a).save()


def test_one_match_per_court_per_round():
    flight = add_flight(make_event())
    a, b, c, d = (add_team(flight, n) for n in "ABCD")
    make_match(flight, a, b).save()
    with pytest.raises(IntegrityError), transaction.atomic():
        make_match(flight, c, d).save()


def test_match_team_from_other_flight_fails_clean():
    event = make_event()
    flight = add_flight(event)
    other = add_flight(event, format="womens")
    a, b = add_team(flight, "A"), add_team(other, "B")
    with pytest.raises(ValidationError):
        make_match(flight, a, b).full_clean()


def test_match_winner_must_be_in_match():
    flight = add_flight(make_event())
    a, b, c = (add_team(flight, n) for n in "ABC")
    with pytest.raises(ValidationError):
        make_match(flight, a, b, winner=c).full_clean()


def test_match_week_must_belong_to_flights_event():
    flight = add_flight(make_event())
    other_event = make_event(name="Other")
    a, b = add_team(flight, "A"), add_team(flight, "B")
    with pytest.raises(ValidationError):
        make_match(flight, a, b, event=other_event).full_clean()


def test_player_email_unique_per_org_but_blank_allowed():
    org = Organization.objects.create(name="Org")
    add_player(org, "One")
    add_player(org, "Two")  # two blank emails are fine
    add_player(org, "Three", "p@x.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        add_player(org, "Four", "p@x.com")


def test_invite_token_is_long_random_and_expires_in_7_days():
    org = Organization.objects.create(name="Org")
    i = Invite.objects.create(organization=org, email="p@x.com", role="player")
    assert len(i.token) >= 40 and not i.is_expired()
    assert i.is_expired(now=timezone.now() + timedelta(days=8))


def test_deleting_event_removes_its_flights_teams_and_matches():
    event = make_event()
    flight = add_flight(event)
    a, b = add_team(flight, "A"), add_team(flight, "B")
    make_match(flight, a, b).save()
    event.delete()
    assert not Flight.objects.exists()
    assert not Team.objects.exists()
    assert not Match.objects.exists()
    assert not Event.objects.exists()


def test_deleting_organization_cascades_everything():
    event = make_event()
    flight = add_flight(event)
    a, b = add_team(flight, "A"), add_team(flight, "B")
    make_match(flight, a, b).save()
    event.organization.delete()
    assert not Event.objects.exists()
    assert not Player.objects.exists()
    assert not Team.objects.exists()
    assert not TeamMember.objects.exists()
    assert not Match.objects.exists()


def test_cannot_delete_player_on_a_team():
    team = add_team(add_flight(make_event()), "Dinkers")
    player = team.players.first()
    with pytest.raises(RestrictedError):
        player.delete()
