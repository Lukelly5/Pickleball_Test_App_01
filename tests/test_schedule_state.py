from datetime import date

from django.http import QueryDict

from league.display import short_day
from league.models import Week
from league.schedule_page import (
    ScheduleState,
    WeekPill,
    default_week,
    next_game_night,
    read_state,
    tonight_week,
    week_pills,
)
from tests.factories import add_flight, make_event
import pytest

pytestmark = pytest.mark.django_db


def MAR(d):
    return date(2027, 3, d)


@pytest.fixture
def setup():
    event = make_event(weeks=4)
    flight = add_flight(event)
    return event, flight, list(event.weeks.all())


def cancel(event, number):
    Week.objects.filter(event=event, number=number).update(status=Week.Status.CANCELLED)
    return list(event.weeks.all())


def test_short_day():
    assert short_day(date(2026, 12, 1)) == "Tue Dec 1"
    assert short_day(MAR(2)) == "Tue Mar 2"


def test_default_today(setup):
    assert default_week(setup[2], MAR(9)) == 2


def test_default_next(setup):
    assert default_week(setup[2], MAR(10)) == 3


def test_default_before_season(setup):
    assert default_week(setup[2], date(2027, 1, 1)) == 1


def test_default_after_season(setup):
    assert default_week(setup[2], date(2027, 6, 1)) == 4


def test_default_no_dates(setup):
    event = setup[0]
    Week.objects.update(date=None)
    assert default_week(list(event.weeks.all()), MAR(9)) == 1


def test_default_no_weeks():
    assert default_week([], MAR(9)) is None


def test_game_night_opens_tonight(setup):
    assert read_state(setup[0], QueryDict(""), MAR(9)) == ScheduleState(2, "", None, True)


def test_junk_week_on_game_night_opens_tonight(setup):
    assert read_state(setup[0], QueryDict("week=abc"), MAR(9)).tonight is True


def test_week_param_wins(setup):
    assert read_state(setup[0], QueryDict("week=3"), MAR(9)) == ScheduleState(3, "", None, False)


def test_view_tonight_clears_filters(setup):
    e, f, _ = setup
    s = read_state(e, QueryDict(f"view=tonight&week=4&flight={f.pk}"), MAR(9))
    assert s == ScheduleState(2, "", None, True)


def test_view_tonight_no_game(setup):
    assert read_state(setup[0], QueryDict("view=tonight"), MAR(10)) == ScheduleState(None, "", None, True)


def test_filter_without_week_on_game_night_stays_filtered(setup):
    e, f, _ = setup
    assert read_state(e, QueryDict(f"flight={f.pk}"), MAR(9)) == ScheduleState(2, "", f.pk, False)


def test_cancelled_today_is_not_tonight(setup):
    e = setup[0]
    weeks = cancel(e, 2)
    s = read_state(e, QueryDict(""), MAR(9))
    assert s.tonight is False and s.week == 3
    assert next_game_night(weeks, MAR(9)).number == 3 and tonight_week(weeks, MAR(9)) is None


def test_junk_filters_fall_back(setup):
    assert read_state(setup[0], QueryDict("week=2&division=pro&flight=999"), MAR(9)) == ScheduleState(2, "", None, False)


def test_flight_outside_division_dropped(setup):
    e, _, _ = setup
    adv = add_flight(e, level="advanced")
    s = read_state(e, QueryDict(f"week=2&division=intermediate&flight={adv.pk}"), MAR(9))
    assert s == ScheduleState(2, "intermediate", None, False)


def test_pills(setup):
    weeks = cancel(setup[0], 3)
    pills = week_pills(weeks)
    assert [p.label for p in pills] == ["Wk1", "Wk2", "Wk3 · Cancelled", "Wk4"]
    assert [p.cancelled for p in pills] == [False, False, True, False]
    assert pills[0] == WeekPill(1, "Wk1", False)
