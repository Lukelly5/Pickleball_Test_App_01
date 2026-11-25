"""Who may score which match, and the save, forfeit and clear writes.

Every write runs in one transaction behind the Event row lock, then re-reads
the match and re-checks permissions under that lock. Rules take `today`; only
views read the clock.
"""

from collections.abc import Iterable
from datetime import date

from django.core.exceptions import PermissionDenied
from django.db import transaction

from accounts.roles import player_for
from league.models import Event, GameScore, Match, Week
from league.schedule_edits import GONE
from league.scoring import Format, ScoreCheck, check_score

ADMIN_LOCKED = "An admin has already scored this match."


class ScoreRefused(Exception):
    """str(exc) is the user-facing message."""


def editor_name(user) -> str:
    if user is None:
        return ""
    player = getattr(user, "player", None)
    if player is not None:
        return player.name
    return user.get_full_name() or user.email


def admin_locked(match: Match) -> bool:
    return bool(match.last_edited_by_id and match.last_edited_by.is_admin)


def _playable(event: Event, match: Match) -> bool:
    return (
        event.status in (Event.Status.PUBLISHED, Event.Status.COMPLETED)
        and match.week.status != Week.Status.CANCELLED
        and match.status in (Match.Status.SCHEDULED, Match.Status.FINAL)
        and not match.team_a.withdrawn_at
        and not match.team_b.withdrawn_at
    )


def _is_org_admin(user, event: Event) -> bool:
    return bool(user.is_admin and user.organization_id == event.organization_id)


def _player_team_ids(user) -> frozenset[int]:
    player = player_for(user)
    if player is None:
        return frozenset()
    return frozenset(player.teams.values_list("pk", flat=True))


def _can_score(user, event: Event, match: Match, today: date, team_ids) -> bool:
    if not _playable(event, match):
        return False
    if user.is_admin:
        return _is_org_admin(user, event)
    return (
        event.status == Event.Status.PUBLISHED
        and event.player_score_entry
        and bool({match.team_a_id, match.team_b_id} & team_ids)
        and (match.week.date is None or match.week.date <= today)
        and not admin_locked(match)
    )


def _event_of(match: Match) -> Event:
    return match.flight.division.event


def can_score(user, match: Match, today: date) -> bool:
    event = _event_of(match)
    team_ids = frozenset() if user.is_admin else _player_team_ids(user)
    return _can_score(user, event, match, today, team_ids)


def can_manage(user, match: Match) -> bool:
    event = _event_of(match)
    return _is_org_admin(user, event) and _playable(event, match)


def scorable_ids(user, event: Event, match_ids: Iterable[int], today: date) -> frozenset[int]:
    matches = Match.objects.filter(pk__in=list(match_ids), flight__division__event=event).select_related(
        "week", "team_a", "team_b", "last_edited_by"
    )
    team_ids = frozenset() if user.is_admin else _player_team_ids(user)
    return frozenset(m.pk for m in matches if _can_score(user, event, m, today, team_ids))


def _lock(event: Event, match_id: int) -> tuple[Event, Match]:
    """Lock the event, then re-read the match. Must run in a transaction."""
    locked = Event.objects.select_for_update().get(pk=event.pk)
    match = (
        Match.objects.filter(pk=match_id, flight__division__event=locked)
        .select_related("week", "team_a", "team_b", "last_edited_by")
        .first()
    )
    if match is None:
        raise ScoreRefused(GONE)
    return locked, match


def _require_manager(user, event: Event, match: Match) -> None:
    if not (_is_org_admin(user, event) and _playable(event, match)):
        raise PermissionDenied


def _finish(match: Match, user, *, winner_id, forfeited_by_id, status) -> None:
    match.winner_id = winner_id
    match.forfeited_by_id = forfeited_by_id
    match.status = status
    match.last_edited_by = user
    match.save(update_fields=["winner", "forfeited_by", "status", "last_edited_by", "updated_at"])


def save_score(
    event: Event, match_id: int, user, raw: list[tuple[str, str]], today: date, *, anyway: bool = False
) -> tuple[Match | None, ScoreCheck]:
    with transaction.atomic():
        locked, match = _lock(event, match_id)
        team_ids = frozenset() if user.is_admin else _player_team_ids(user)
        if not _can_score(user, locked, match, today, team_ids):
            if admin_locked(match) and not user.is_admin:
                raise ScoreRefused(ADMIN_LOCKED)
            raise PermissionDenied
        check = check_score(
            Format.of(locked), raw, (match.team_a.name, match.team_b.name), admin=user.is_admin
        )
        if not check.can_save or (check.save_anyway and not anyway):
            return None, check
        match.games.all().delete()
        GameScore.objects.bulk_create(
            GameScore(match=match, game_no=n, points_a=a, points_b=b)
            for n, (a, b) in enumerate(check.games_to_save(), start=1)
        )
        winner_id = match.team_a_id if check.leader == "a" else match.team_b_id
        _finish(match, user, winner_id=winner_id, forfeited_by_id=None, status=Match.Status.FINAL)
        return match, check


def save_forfeit(event: Event, match_id: int, user, forfeited_team_id: int) -> Match:
    with transaction.atomic():
        locked, match = _lock(event, match_id)
        _require_manager(user, locked, match)
        if forfeited_team_id not in (match.team_a_id, match.team_b_id):
            raise ScoreRefused("Choose the team that forfeited.")
        other = match.team_b_id if forfeited_team_id == match.team_a_id else match.team_a_id
        match.games.all().delete()
        _finish(match, user, winner_id=other, forfeited_by_id=forfeited_team_id, status=Match.Status.FINAL)
        return match


def clear_score(event: Event, match_id: int, user) -> Match:
    with transaction.atomic():
        locked, match = _lock(event, match_id)
        _require_manager(user, locked, match)
        match.games.all().delete()
        _finish(match, user, winner_id=None, forfeited_by_id=None, status=Match.Status.SCHEDULED)
        return match
