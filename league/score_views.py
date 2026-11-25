"""The score page: form, save, forfeit and clear (works without JavaScript)."""

from dataclasses import replace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .event_views import _render, draft_guard, member_event
from .filters import to_int
from .models import Match
from .score_edits import ScoreRefused, can_manage, can_score, clear_score, save_forfeit, save_score
from .scoring import Format, Message, ScoreCheck, check_score, raw_games

FORFEIT_REFUSAL = "Choose the team that forfeited."


def _names(match: Match) -> tuple[str, str]:
    return match.team_a.name, match.team_b.name


def _saved_check(event, match: Match, admin: bool) -> ScoreCheck:
    """The check for the saved games, for a fresh form (no messages are shown)."""
    fmt = Format.of(event)
    raw = [("", "")] * fmt.best_of
    for g in match.games.all():
        if g.game_no <= fmt.best_of:
            raw[g.game_no - 1] = (str(g.points_a), str(g.points_b))
    return check_score(fmt, raw, _names(match), admin=admin)


def _refused(check: ScoreCheck, text: str) -> ScoreCheck:
    return replace(check, messages=check.messages + (Message(text, True),))


def render_score(
    request,
    event,
    match: Match,
    check: ScoreCheck | None,
    *,
    step: str = "form",
    confirm: str | None = None,
    status: int = 200,
):
    """check=None is a fresh form: saved values, and no messages shown."""
    admin = request.user.is_admin
    show_messages = check is not None
    if check is None:
        check = _saved_check(event, match, admin)
    fmt = Format.of(event)
    rows = [
        {
            "n": n,
            "a": check.values[n - 1][0],
            "b": check.values[n - 1][1],
            "winner": check.game_winners[n - 1] if n <= len(check.game_winners) else None,
        }
        for n in range(1, fmt.best_of + 1)
    ]
    partial = "league/score/_forfeit.html" if step == "forfeit" else "league/score/_form.html"
    context = {
        "event": event,
        "match": match,
        "match_teams": (match.team_a, match.team_b),
        "format_label": fmt.label,
        "rows": rows,
        "check": check,
        "messages_shown": check.messages if show_messages else (),
        "blocked": show_messages and bool(check.messages) and not admin,
        "is_admin": admin,
        "scored": match.status == Match.Status.FINAL,
        "confirm": confirm,
        "step": step,
        "partial": partial,
        "week_url": reverse("event_schedule", args=[event.pk]) + f"?week={match.week.number}",
    }
    response = _render(request, "league/score/page.html", partial, context)
    response.status_code = status
    return response


def _match(event, match_pk: int) -> Match:
    return get_object_or_404(
        Match.objects.select_related(
            "week", "team_a", "team_b", "last_edited_by", "flight__division__event"
        ).prefetch_related("games"),
        pk=match_pk,
        flight__division__event=event,
    )


def _back(event, match: Match):
    return redirect(reverse("event_schedule", args=[event.pk]) + f"?week={match.week.number}")


def _load(request, pk: int, match_pk: int):
    """(event, match, guard); the guard is a redirect when the event is a draft."""
    event = member_event(request, pk)
    if guard := draft_guard(request, event):
        return event, None, guard
    return event, _match(event, match_pk), None


def _read_check(request, event, match: Match) -> ScoreCheck:
    fmt = Format.of(event)
    return check_score(fmt, raw_games(request.POST, fmt.best_of), _names(match), admin=request.user.is_admin)


@login_required
@require_http_methods(["GET", "POST"])
def match_score(request, pk: int, match_pk: int):
    event, match, guard = _load(request, pk, match_pk)
    if guard:
        return guard
    today = timezone.localdate()
    if not can_score(request.user, match, today):
        raise PermissionDenied
    if request.method == "GET":
        return render_score(request, event, match, None)

    fmt = Format.of(event)
    raw = raw_games(request.POST, fmt.best_of)
    try:
        saved, check = save_score(
            event, match.pk, request.user, raw, today, anyway=request.POST.get("anyway") == "1"
        )
    except ScoreRefused as refusal:
        return render_score(request, event, match, _refused(_read_check(request, event, match), str(refusal)))
    if saved is None:
        return render_score(request, event, match, check)
    messages.success(request, "Score saved")
    return _back(event, saved)


@login_required
@require_POST
def match_score_check(request, pk: int, match_pk: int):
    event, match, guard = _load(request, pk, match_pk)
    if guard:
        return guard
    if not can_score(request.user, match, timezone.localdate()):
        raise PermissionDenied
    return render_score(request, event, match, _read_check(request, event, match))


@login_required
@require_http_methods(["GET", "POST"])
def match_forfeit(request, pk: int, match_pk: int):
    event, match, guard = _load(request, pk, match_pk)
    if guard:
        return guard
    if not can_manage(request.user, match):
        raise PermissionDenied
    if request.method == "GET":
        return render_score(request, event, match, None, step="forfeit")
    team_id = to_int(request.POST.get("team"))
    try:
        if team_id is None:
            raise ScoreRefused(FORFEIT_REFUSAL)
        saved = save_forfeit(event, match.pk, request.user, team_id)
    except ScoreRefused as refusal:
        check = _refused(_saved_check(event, match, True), str(refusal))
        return render_score(request, event, match, check, step="forfeit")
    messages.success(request, "Forfeit saved")
    return _back(event, saved)


@login_required
def match_score_clear(request, pk: int, match_pk: int):
    event, match, guard = _load(request, pk, match_pk)
    if guard:
        return guard
    if not can_manage(request.user, match):
        raise PermissionDenied
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if request.POST.get("confirm") != "1":
        return render_score(request, event, match, _read_check(request, event, match), confirm="clear")
    try:
        saved = clear_score(event, match.pk, request.user)
    except ScoreRefused as refusal:
        return render_score(request, event, match, _refused(_read_check(request, event, match), str(refusal)))
    messages.success(request, "Score cleared")
    return _back(event, saved)
