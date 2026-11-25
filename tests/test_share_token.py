import pytest

from league import schedule_edits as edits
from league.models import Event
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, make_event

pytestmark = pytest.mark.django_db


def built_event():
    event = make_event(weeks=4, courts=3)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in ("Dinkers", "Smashers", "Lobsters", "Kings"):
        add_team(flight, n)
    generate_event(event)
    return event


def test_ensure_creates_once():
    e = make_event()
    t = e.ensure_share_token()
    assert t and len(t) >= 40
    e.refresh_from_db()
    assert e.share_token == t
    assert e.ensure_share_token() == t


def test_reset_changes_token():
    e = make_event()
    old = e.ensure_share_token()
    new = e.reset_share_token()
    e.refresh_from_db()
    assert new != old and e.share_token == new


def test_publish_sets_token():
    event = built_event()
    edits.publish(event)
    assert event.share_token
    event.refresh_from_db()
    assert event.status == "published" and event.share_token


def test_publish_keeps_existing_token():
    event = built_event()
    event.share_token = "keep"
    event.save()
    edits.publish(event)
    event.refresh_from_db()
    assert event.status == "published" and event.share_token == "keep"


def test_refused_publish_sets_no_token():
    event = built_event()
    Event.objects.filter(pk=event.pk).update(schedule_stale=True)
    event.refresh_from_db()
    with pytest.raises(edits.EditRefused):
        edits.publish(event)
    event.refresh_from_db()
    assert event.share_token is None
