from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from league.models import Event, Flight, GameScore, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, make_event

pytestmark = pytest.mark.django_db


@pytest.fixture
def debug_on(settings):
    settings.DEBUG = True  # seed_demo refuses to run with DEBUG off


def two_team_match(event):
    flight = add_flight(event, games=(1,) * event.weeks.count())
    a, b = add_team(flight, "A"), add_team(flight, "B")
    return Match.objects.create(flight=flight, week=event.weeks.get(number=1),
                                round_no=1, court_no=1, team_a=a, team_b=b)


def test_defaults():
    event = make_event()
    assert (event.schedule_stale, event.setup_step) == (False, 0)
    assert add_flight(event).games_plan == "custom"


def test_has_scores_game_score_final_and_forfeit():
    event = make_event(weeks=1)
    match = two_team_match(event)
    assert not event.has_scores()
    GameScore.objects.create(match=match, game_no=1, points_a=11, points_b=5)
    assert event.has_scores()
    match.games.all().delete(); match.status = "final"; match.save()
    assert event.has_scores()
    match.status = "scheduled"; match.forfeited_by = match.team_a; match.save()
    assert event.has_scores()


def test_set_week_count_redates_every_week():
    event = make_event(weeks=2)                      # starts 2027-03-02
    event.start_date = date(2027, 3, 9); event.save()
    event.set_week_count(3)
    assert [w.date for w in event.weeks.all()] == [date(2027, 3, 9), date(2027, 3, 16), date(2027, 3, 23)]


def test_set_week_count_blocked_once_scored():
    event = make_event(weeks=1)
    GameScore.objects.create(match=two_team_match(event), game_no=1, points_a=11, points_b=5)
    with pytest.raises(ValidationError, match="Scores have been entered, so the weeks can't change."):
        event.set_week_count(2)


def test_generate_clears_stale():
    event = make_event(weeks=1)
    two_team_match(event).delete()
    Event.objects.filter(pk=event.pk).update(schedule_stale=True)
    generate_event(event)
    event.refresh_from_db()
    assert event.schedule_stale is False and Match.objects.filter(flight__division__event=event).count() == 1


def test_seed_events_are_fully_set_up(debug_on):
    call_command("seed_demo")
    assert set(Event.objects.values_list("setup_step", flat=True)) == {5}
