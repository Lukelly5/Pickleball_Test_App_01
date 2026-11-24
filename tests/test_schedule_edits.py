import pytest
from django.utils import timezone

import scheduler
from league import schedule_edits as edits
from league.models import Event, Match, Team, Week
from league.scheduling import generate_event, load_schedule
from league.setup_preview import plan_views
from scheduler import ScheduleError
from tests.factories import add_flight, add_player, add_team, make_event, score

pytestmark = pytest.mark.django_db

GONE = "That game is no longer on the schedule. Refresh and try again."


def build(name="Spring Tuesday League", team_names=("Dinkers", "Smashers", "Lobsters", "Kings")):
    event = make_event(name=name, weeks=4, courts=3)
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in team_names:
        add_team(flight, n)
    generate_event(event)
    return event, flight


def rows(event):
    return Match.objects.filter(flight__division__event=event)


def snapshot(event):
    return sorted(
        rows(event).values_list(
            "id", "week_id", "round_no", "court_no", "team_a_id", "team_b_id", "status"
        )
    )


def week1(event):
    return list(rows(event).filter(week__number=1).order_by("round_no", "court_no"))


def slot(m):
    return (1, m.round_no, m.court_no)


def free_slot(event):
    taken = {(m.round_no, m.court_no) for m in week1(event)}
    for r in range(1, max(r for r, _ in taken) + 1):
        for c in range(1, event.courts + 1):
            if (r, c) not in taken:
                return r, c
    raise AssertionError("no free slot")


def engine_accepts(fn):
    try:
        fn()
    except scheduler.SwapConflict:
        return False
    return True


def swappable_pair(event):
    schedule = load_schedule(event)[0]
    ms = week1(event)
    for i, a in enumerate(ms):
        for b in ms[i + 1 :]:
            if engine_accepts(lambda: scheduler.swap_games(schedule, slot(a), slot(b))):
                return a, b
    raise AssertionError("no swappable pair")


def test_swap_games_trades_slots():
    event, _ = build()
    a, b = swappable_pair(event)
    before = {r[0]: r for r in snapshot(event)}
    edits.swap_games(event, a.pk, b.pk)
    after = {r[0]: r for r in snapshot(event)}
    assert after[a.pk][2:4] == (b.round_no, b.court_no)
    assert after[b.pk][2:4] == (a.round_no, a.court_no)
    for pk in before:
        if pk not in (a.pk, b.pk):
            assert before[pk] == after[pk]


def test_swap_teams_flip_swaps_the_two_teams():
    event, _ = build()
    a = week1(event)[0]
    ta, tb = a.team_a_id, a.team_b_id
    edits.swap_teams(event, (a.pk, "a"), (a.pk, "b"))
    a.refresh_from_db()
    assert (a.team_a_id, a.team_b_id) == (tb, ta)


def test_swap_teams_trades_teams_across_two_matches():
    event, _ = build()
    schedule = load_schedule(event)[0]
    ms = week1(event)
    pair = next(
        (x, y)
        for x in ms
        for y in ms
        if x.pk < y.pk
        and engine_accepts(
            lambda: scheduler.swap_teams(schedule, (slot(x), "a"), (slot(y), "a"))
        )
    )
    x, y = pair
    xa, ya = x.team_a_id, y.team_a_id
    edits.swap_teams(event, (x.pk, "a"), (y.pk, "a"))
    x.refresh_from_db()
    y.refresh_from_db()
    assert (x.team_a_id, y.team_a_id) == (ya, xa)


def test_move_game_writes_slot():
    event, _ = build()
    r, c = free_slot(event)
    schedule = load_schedule(event)[0]
    moved = next(
        m
        for m in week1(event)
        if engine_accepts(lambda: scheduler.move_game(schedule, slot(m), (1, r, c)))
    )
    edits.move_game(event, moved.pk, r, c)
    moved.refresh_from_db()
    assert (moved.round_no, moved.court_no) == (r, c)


def test_move_game_refuses_round_or_court_below_one():
    event, _ = build()
    m = week1(event)[0]
    before = snapshot(event)
    with pytest.raises(edits.EditRefused, match="Rounds 1"):
        edits.move_game(event, m.pk, 0, 1)
    with pytest.raises(edits.EditRefused, match="there are only 3 courts"):
        edits.move_game(event, m.pk, 1, 0)
    assert snapshot(event) == before


def test_engine_clash_is_passed_through():
    event, _ = build()
    schedule = load_schedule(event)[0]
    ms = week1(event)
    taken = {(x.round_no, x.court_no) for x in ms}
    found = None
    for m in ms:
        for r in range(1, max(x.round_no for x in ms) + 1):
            for c in range(1, event.courts + 1):
                if (r, c) in taken:
                    continue
                try:
                    scheduler.move_game(schedule, slot(m), (1, r, c))
                except scheduler.SwapConflict as exc:
                    found = (m, r, c, str(exc))
    assert found, "expected a clashing move"
    m, r, c, msg = found
    before = snapshot(event)
    with pytest.raises(edits.EditRefused) as err:
        edits.move_game(event, m.pk, r, c)
    assert str(err.value) == msg
    assert snapshot(event) == before


@pytest.mark.parametrize(
    "case",
    ["other_event", "unknown", "scored", "withdrawn", "cancelled_week", "cancelled_target"],
)
def test_refusals_change_nothing(case):
    event, _ = build()
    other, _ = build(name="Other", team_names=("W", "X", "Y", "Z"))
    foreign = rows(other).first()
    a, b = week1(event)[:2]

    if case == "other_event":
        msg = GONE

        def call():
            edits.swap_games(event, a.pk, foreign.pk)

    elif case == "unknown":
        msg = GONE

        def call():
            edits.swap_games(event, a.pk, 999999)

    elif case == "scored":
        score(a)
        msg = "Can't change a game that already has a score."

        def call():
            edits.swap_games(event, a.pk, b.pk)

    elif case == "withdrawn":
        Team.objects.filter(pk=a.team_a_id).update(withdrawn_at=timezone.now())
        msg = "Can't change a game with a withdrawn team."

        def call():
            edits.swap_games(event, a.pk, b.pk)

    elif case == "cancelled_week":
        Week.objects.filter(event=event, number=1).update(status=Week.Status.CANCELLED)
        msg = "Week 1 is cancelled, so its games can't change."

        def call():
            edits.swap_games(event, a.pk, b.pk)

    else:
        r, c = free_slot(event)
        Match.objects.filter(pk=b.pk).update(
            status=Match.Status.CANCELLED, round_no=r, court_no=c
        )
        msg = f"Can't move: Court {c} in Round {r} already has a game."

        def call():
            edits.move_game(event, a.pk, r, c)

    before, other_before = snapshot(event), snapshot(other)
    with pytest.raises(edits.EditRefused) as err:
        call()
    assert str(err.value) == msg
    assert snapshot(event) == before
    assert snapshot(other) == other_before


def test_swap_games_rolls_back_on_failure(monkeypatch):
    event, _ = build()
    a, b = swappable_pair(event)
    before = snapshot(event)
    real_save = Match.save
    calls = {"n": 0}

    def flaky(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real_save(self, *args, **kwargs)

    monkeypatch.setattr(Match, "save", flaky)
    with pytest.raises(RuntimeError):
        edits.swap_games(event, a.pk, b.pk)
    monkeypatch.undo()
    assert calls["n"] == 2
    assert not rows(event).filter(court_no__gt=event.courts).exists()
    assert snapshot(event) == before


def test_publish():
    event, _ = build()
    edits.publish(event)
    event.refresh_from_db()
    assert event.status == "published"
    edits.publish(event)  # already published: no-op
    event.refresh_from_db()
    assert event.status == "published"


def test_publish_refuses_stale():
    event, _ = build()
    Event.objects.filter(pk=event.pk).update(schedule_stale=True)
    event.refresh_from_db()
    with pytest.raises(edits.EditRefused) as err:
        edits.publish(event)
    assert str(err.value) == "Regenerate first: inputs changed since this schedule was made."
    event.refresh_from_db()
    assert event.status == "draft"


def test_publish_refuses_without_matches():
    event = make_event()
    with pytest.raises(edits.EditRefused) as err:
        edits.publish(event)
    assert str(err.value) == "Generate a schedule before publishing."


def test_regenerate():
    event, _ = build()
    old = {m.pk for m in rows(event)}
    Event.objects.filter(pk=event.pk).update(schedule_stale=True)
    event.refresh_from_db()
    schedule = edits.regenerate(event)
    assert len(schedule.matches) == rows(event).count()
    assert not old & {m.pk for m in rows(event)}
    event.refresh_from_db()
    assert event.schedule_stale is False


def test_regenerate_blocked_leaves_matches():
    event, flight = build()
    add_team(flight, "Solo", players=(add_player(event.organization, "Lone"),))
    blocker = next(v.blocker for v in plan_views(event)[0] if v.blocker)
    before = snapshot(event)
    with pytest.raises(ScheduleError) as err:
        edits.regenerate(event)
    assert str(err.value) == blocker
    assert snapshot(event) == before


def test_edits_do_not_mark_stale():
    event, _ = build()
    a, b = swappable_pair(event)
    edits.swap_games(event, a.pk, b.pk)
    event.refresh_from_db()
    assert event.schedule_stale is False
