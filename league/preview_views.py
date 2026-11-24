"""The Schedule Preview page (P4): thin views over league.preview."""

from urllib.parse import urlencode

import re

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_POST

import scheduler
from accounts.permissions import admin_required
from ui.nav import optional_reverse

from .models import Event, Match
from .preview import PICK_RE, build_board, fairness, parse_state, resolve_click
from .schedule_edits import GONE, EditRefused, move_game, publish, regenerate, swap_games, swap_teams

TEAM_KEY = re.compile(r"^t(\d+)([ab])$")
OPEN_KEY = re.compile(r"^o(\d+)-(\d+)$")


def preview_event(request, pk: int) -> Event:
    """The event, only if it is in the admin's organization (any type)."""
    return get_object_or_404(Event, pk=pk, organization=request.user.organization)


def render_preview(
    request,
    event: Event,
    state: dict,
    *,
    conflict: dict | None = None,
    confirm: str | None = None,
    status: int = 200,
):
    """The board and fairness panel for an HTMX request, else the whole page."""
    board = build_board(event, state)
    if board.flight:
        flight_ids = {board.flight}
    elif board.division:
        flight_ids = {pk for pk, _ in board.flights}
    else:
        flight_ids = None
    filters = {k: v for k, v in (("division", board.division), ("flight", board.flight)) if v}
    context = {
        "event": event,
        "board": board,
        "fairness": fairness(event, board.week, flight_ids),
        "conflict": conflict,
        "confirm": confirm,
        "has_matches": Match.objects.filter(flight__division__event=event).exists(),
        "query": urlencode({"week": board.week, **filters}),
        "filter_query": urlencode(filters),
    }
    # htmx's history-restore request also sends HX-Request; it needs the whole page.
    partial = request.headers.get("HX-Request") and not request.headers.get(
        "HX-History-Restore-Request"
    )
    template = "league/preview/_board.html" if partial else "league/preview/page.html"
    response = render(request, template, context, status=status)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


@admin_required
def event_preview(request, pk: int):
    event = preview_event(request, pk)
    return render_preview(request, event, parse_state(event, request.GET))


def _preview_url(event: Event, state: dict, pick: str | None = None) -> str:
    """The preview URL for this week and filters, with a pick only when given."""
    params = {"week": state["week"]}
    if state["division"]:
        params["division"] = state["division"]
    if state["flight"]:
        params["flight"] = state["flight"]
    if pick:
        params["pick"] = pick
    return f"{reverse('event_preview', args=[event.pk])}?{urlencode(params)}"


def _tile_key(target: str) -> str:
    """The tile that shows a conflict: a team key belongs to its game's tile."""
    found = TEAM_KEY.match(target)
    return f"g{found.group(1)}" if found else target


def _team_key(key: str) -> tuple[int, str]:
    found = TEAM_KEY.match(key)
    return int(found.group(1)), found.group(2)


def _act(event: Event, action: str, pick: str, target: str) -> None:
    """Run a write action. Keys come from the board, so they always decode."""
    if action == "swap_games":
        swap_games(event, int(pick[1:]), int(target[1:]))
    elif action == "swap_teams":
        swap_teams(event, _team_key(pick), _team_key(target))
    else:
        rnd, court = OPEN_KEY.match(target).groups()
        move_game(event, int(pick[1:]), int(rnd), int(court))


@admin_required
@require_POST
def event_preview_edit(request, pk: int):
    """A click: select a pick, or act on it (swap games, swap teams, move)."""
    event = preview_event(request, pk)
    state = parse_state(event, request.POST)
    target = request.POST.get("target", "")
    htmx = bool(request.headers.get("HX-Request"))

    def reply(url: str, new_state: dict, **kwargs):
        if not htmx:
            return redirect(url)
        response = render_preview(request, event, new_state, **kwargs)
        response["HX-Push-Url"] = url
        return response

    board = build_board(event, state)
    if PICK_RE.match(request.POST.get("pick", "")) and board.pick is None:
        # The pick names a game that is gone (or can no longer be clicked).
        return render_preview(
            request, event, {**state, "pick": None}, conflict={"key": _tile_key(target), "message": GONE}
        )

    action, value = resolve_click(board, target)
    if action == "select":
        return reply(_preview_url(event, state, value), {**state, "pick": value})

    clear = {**state, "pick": None}
    try:
        _act(event, action, board.pick, value)
    except EditRefused as exc:
        return render_preview(request, event, clear, conflict={"key": _tile_key(target), "message": str(exc)})
    return reply(_preview_url(event, state), clear)


def regenerated_message(games: int, weeks: int) -> str:
    return (
        f"Schedule regenerated · {games} {'game' if games == 1 else 'games'}"
        f" over {weeks} {'week' if weeks == 1 else 'weeks'}"
    )


@admin_required
@require_POST
def event_preview_regenerate(request, pk: int):
    event = preview_event(request, pk)
    state = parse_state(event, request.GET)
    if request.POST.get("confirm") != "1":
        return render_preview(request, event, state, confirm="regenerate")
    try:
        schedule = regenerate(event)
    except (scheduler.ScheduleError, EditRefused) as exc:
        messages.error(request, str(exc))
    else:
        games = len(schedule.matches)
        weeks = len({m.week for m in schedule.matches})
        messages.success(request, regenerated_message(games, weeks))
    return redirect(_preview_url(event, state))


@admin_required
@require_POST
def event_preview_publish(request, pk: int):
    event = preview_event(request, pk)
    state = parse_state(event, request.GET)
    if request.POST.get("confirm") != "1":
        return render_preview(request, event, state, confirm="publish")
    try:
        publish(event)
    except EditRefused as exc:
        messages.error(request, str(exc))
        return redirect(_preview_url(event, state))
    messages.success(request, f"{event.name} published")
    return redirect(optional_reverse("event_schedule", event.pk) or reverse("event_list"))
