"""Database edits to a generated schedule: swap, move, publish, regenerate.

Each write runs in one transaction behind the Event row lock. The pure
`scheduler` engine decides whether an edit is legal; this module maps match
rows to engine slots and writes only the rows that changed.
"""

import scheduler
from django.db import transaction

from league.models import Event, Match
from league.scheduling import generate_event, load_schedule
from league.setup_preview import plan_views

GONE = "That game is no longer on the schedule. Refresh and try again."


class EditRefused(Exception):
    """str(exc) is the user-facing message."""


def scored_match_ids(event: Event) -> set[int]:
    """Matches that are final, forfeited, or have any game score."""
    return event.scored_match_ids()


def _locked_matches(event: Event, ids) -> tuple[Event, dict[int, Match]]:
    """Lock the event, then fetch and vet the matches. Must run in a transaction."""
    locked = Event.objects.select_for_update().get(pk=event.pk)
    wanted = set(ids)
    found = {
        m.pk: m
        for m in Match.objects.filter(
            pk__in=wanted, flight__division__event=locked
        ).select_related("week", "team_a", "team_b")
    }
    if wanted - found.keys():
        raise EditRefused(GONE)
    scored = scored_match_ids(locked)
    for pk in ids:
        m = found[pk]
        if m.pk in scored:
            raise EditRefused("Can't change a game that already has a score.")
        if m.team_a.withdrawn_at or m.team_b.withdrawn_at:
            raise EditRefused("Can't change a game with a withdrawn team.")
        if m.week.status == m.week.Status.CANCELLED:
            raise EditRefused(f"Week {m.week.number} is cancelled, so its games can't change.")
    return locked, found


def _slot(m: Match) -> scheduler.swap.Slot:
    return (m.week.number, m.round_no, m.court_no)


def _run(fn, *args):
    """Run an engine edit; a missing slot or conflict becomes a refusal."""
    try:
        return fn(*args)
    except scheduler.SwapConflict as exc:
        raise EditRefused(str(exc)) from exc
    except KeyError as exc:  # row isn't SCHEDULED/FINAL, so the engine can't see it
        raise EditRefused(GONE) from exc


def swap_games(event: Event, match_a: int, match_b: int) -> None:
    with transaction.atomic():
        locked, found = _locked_matches(event, [match_a, match_b])
        a, b = found[match_a], found[match_b]
        schedule, _ = load_schedule(locked)
        _run(scheduler.swap_games, schedule, _slot(a), _slot(b))
        if a.pk == b.pk:
            return
        a_round, a_court = a.round_no, a.court_no
        # Park A on the spare court so the unique slot constraint never trips.
        a.court_no = locked.courts + 1
        a.save(update_fields=["court_no", "updated_at"])
        b_round, b_court = b.round_no, b.court_no
        b.round_no, b.court_no = a_round, a_court
        b.save(update_fields=["round_no", "court_no", "updated_at"])
        a.round_no, a.court_no = b_round, b_court
        a.save(update_fields=["round_no", "court_no", "updated_at"])


def swap_teams(event: Event, a: tuple[int, str], b: tuple[int, str]) -> None:
    (id_a, side_a), (id_b, side_b) = a, b
    with transaction.atomic():
        locked, found = _locked_matches(event, [id_a, id_b])
        ma, mb = found[id_a], found[id_b]
        schedule, _ = load_schedule(locked)
        _run(scheduler.swap_teams, schedule, (_slot(ma), side_a), (_slot(mb), side_b))
        if (id_a, side_a) == (id_b, side_b):
            return
        field_a, field_b = f"team_{side_a}_id", f"team_{side_b}_id"
        team_a, team_b = getattr(ma, field_a), getattr(mb, field_b)
        setattr(ma, field_a, team_b)
        setattr(mb, field_b, team_a)
        for m in {ma.pk: ma, mb.pk: mb}.values():
            m.save(update_fields=["team_a", "team_b", "updated_at"])


def move_game(event: Event, match_id: int, round_no: int, court_no: int) -> None:
    with transaction.atomic():
        locked, found = _locked_matches(event, [match_id])
        m = found[match_id]
        target = (m.week.number, round_no, court_no)
        schedule, _ = load_schedule(locked)
        if court_no < 1:
            n = locked.courts
            there = "there is only 1 court" if n == 1 else f"there are only {n} courts"
            raise EditRefused(f"Can't move: {there}.")
        if round_no < 1:
            top = max((g.round_no for g in schedule.week(m.week.number)), default=1)
            raise EditRefused(f"Can't move: Week {m.week.number} only has Rounds 1–{top}.")
        if (m.round_no, m.court_no) != (round_no, court_no) and Match.objects.filter(
            week=m.week, round_no=round_no, court_no=court_no
        ).exists():
            # Includes cancelled/void rows the engine can't see.
            raise EditRefused(
                f"Can't move: Court {court_no} in Round {round_no} already has a game."
            )
        _run(scheduler.move_game, schedule, _slot(m), target)
        if (m.round_no, m.court_no) == (round_no, court_no):
            return
        m.round_no, m.court_no = round_no, court_no
        m.save(update_fields=["round_no", "court_no", "updated_at"])


def publish(event: Event) -> None:
    with transaction.atomic():
        locked = Event.objects.select_for_update().get(pk=event.pk)
        if locked.status != Event.Status.DRAFT:
            return
        if locked.schedule_stale:
            raise EditRefused("Regenerate first: inputs changed since this schedule was made.")
        if not Match.objects.filter(flight__division__event=locked).exists():
            raise EditRefused("Generate a schedule before publishing.")
        Event.objects.filter(pk=locked.pk).update(status=Event.Status.PUBLISHED)
    event.status = Event.Status.PUBLISHED


def regenerate(event: Event) -> scheduler.Schedule:
    views, _ = plan_views(event)
    for v in views:
        if v.blocker:
            raise scheduler.ScheduleError(v.blocker)
    return generate_event(event)
