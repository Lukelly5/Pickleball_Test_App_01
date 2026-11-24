"""The Schedule Preview page (P4): thin views over league.preview."""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, render

from accounts.permissions import admin_required

from .models import Event, Match
from .preview import build_board, fairness, parse_state


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
    template = (
        "league/preview/_board.html"
        if request.headers.get("HX-Request")
        else "league/preview/page.html"
    )
    return render(request, template, context, status=status)


@admin_required
def event_preview(request, pk: int):
    event = preview_event(request, pk)
    return render_preview(request, event, parse_state(event, request.GET))
