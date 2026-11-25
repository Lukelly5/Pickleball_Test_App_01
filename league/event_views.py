"""The event page (Slice 4): Schedule tab, stub tabs, shared with the share link."""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_POST

from accounts.permissions import admin_required
from accounts.roles import player_for
from ui.nav import NavLink, optional_reverse

from .display import short_day
from .models import Event, Team
from .score_edits import scorable_ids
from .schedule_page import build_page, next_game_night, read_state, tonight_week

TABS = (
    ("schedule", "Schedule"),
    ("standings", "Standings"),
    ("teams", "Teams"),
)


def event_tabs(event, active: str, *, token: str | None = None, admin: bool = False) -> list[NavLink]:
    """The underline tabs; share URLs when a token is given, else the event_* names."""

    def url(key: str) -> str:
        return reverse(f"share_{key}", args=[token]) if token else reverse(f"event_{key}", args=[event.pk])

    tabs = [NavLink(label, url(key), "", key == active) for key, label in TABS]
    if admin and token is None:
        settings_url = optional_reverse("event_settings", event.pk)
        if settings_url:
            tabs.append(NavLink("Settings", settings_url, "", active == "settings"))
    return tabs


def member_event(request, pk: int) -> Event:
    """The event, only if it is in the user's organization (any status)."""
    return get_object_or_404(Event, pk=pk, organization_id=request.user.organization_id)


def draft_guard(request, event):
    """None when the event is visible; else a redirect to the preview (admin) or a 404."""
    if event.status != Event.Status.DRAFT:
        return None
    if request.user.is_admin:
        return redirect("event_preview", event.pk)
    raise Http404


def _render(request, template: str, partial: str | None, context: dict):
    # htmx's history-restore request also sends HX-Request; it needs the whole page.
    is_partial = (
        partial
        and request.headers.get("HX-Request")
        and not request.headers.get("HX-History-Restore-Request")
    )
    response = render(request, partial if is_partial else template, context)
    patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])
    return response


def _my_team_ids(request, event, token) -> frozenset[int]:
    player = None if token else player_for(request.user)
    if player is None:
        return frozenset()
    return frozenset(
        Team.objects.filter(flight__division__event=event, members__player=player).values_list(
            "pk", flat=True
        )
    )


def _frame(request, event, active: str, token: str | None) -> dict:
    admin = bool(getattr(request.user, "is_admin", False)) and token is None
    schedule_url = (
        reverse("share_schedule", args=[token]) if token else reverse("event_schedule", args=[event.pk])
    )
    return {
        "schedule_url": schedule_url,
        "event": event,
        "tabs": event_tabs(event, active, token=token, admin=admin),
        "base_template": "base_public.html" if token else "base_app.html",
        "share": token is not None,
        "is_admin": admin,
    }


def render_schedule(request, event, *, token: str | None = None):
    today = timezone.localdate()
    state = read_state(event, request.GET, today)
    page = build_page(event, state, today, _my_team_ids(request, event, token), show_editor=token is None)
    scorable = frozenset()
    if token is None:
        match_ids = [c.match_id for r in page.rounds for c in r.cards]
        scorable = scorable_ids(request.user, event, match_ids, today)
    filters = {} if state.tonight else {
        k: v for k, v in (("division", state.division), ("flight", state.flight)) if v
    }
    context = {
        **_frame(request, event, "schedule", token),
        "page": page,
        "scorable": scorable,
        "swap_body": True,
        "filter_query": urlencode(filters),
        "week_day": short_day(page.week_date) if page.week_date else "",
        "next_day": short_day(page.next_night.date) if page.next_night else "",
    }
    return _render(request, "league/event/page.html", "league/event/_schedule_body.html", context)


def render_coming_soon(request, event, active: str, *, token: str | None = None):
    context = {**_frame(request, event, active, token), "label": dict(TABS)[active]}
    return _render(request, "league/event/coming_soon.html", None, context)


@login_required
def event_schedule(request, pk: int):
    event = member_event(request, pk)
    return draft_guard(request, event) or render_schedule(request, event)


@login_required
def event_standings(request, pk: int):
    event = member_event(request, pk)
    return draft_guard(request, event) or render_coming_soon(request, event, "standings")


@login_required
def event_teams(request, pk: int):
    event = member_event(request, pk)
    return draft_guard(request, event) or render_coming_soon(request, event, "teams")


def _locked(event) -> Event:
    """The event re-read under its row lock; call inside transaction.atomic()."""
    return Event.objects.select_for_update().get(pk=event.pk)


def render_settings(request, event, *, confirm: str | None = None):
    with transaction.atomic():
        token = _locked(event).ensure_share_token()
    context = {
        **_frame(request, event, "settings", None),
        "share_url": request.build_absolute_uri(reverse("share_schedule", args=[token])),
        "confirm": confirm,
    }
    return render(request, "league/event/settings.html", context)


@admin_required
def event_settings(request, pk: int):
    event = member_event(request, pk)
    return draft_guard(request, event) or render_settings(request, event)


@admin_required
@require_POST
def event_share_reset(request, pk: int):
    event = member_event(request, pk)
    if redirect_to_preview := draft_guard(request, event):
        return redirect_to_preview
    if request.POST.get("confirm") != "1":
        return render_settings(request, event, confirm="reset")
    with transaction.atomic():
        _locked(event).reset_share_token()
    messages.success(request, "New share link created.")
    return redirect("event_settings", event.pk)


def shared_event(token: str) -> Event:
    """The event for a share token, only while published or completed."""
    return get_object_or_404(
        Event,
        share_token=token,
        status__in=[Event.Status.PUBLISHED, Event.Status.COMPLETED],
    )


def _noindex(response):
    response["X-Robots-Tag"] = "noindex"
    return response


def share_schedule(request, token: str):
    event = shared_event(token)
    return _noindex(render_schedule(request, event, token=token))


def share_standings(request, token: str):
    event = shared_event(token)
    return _noindex(render_coming_soon(request, event, "standings", token=token))


def share_teams(request, token: str):
    event = shared_event(token)
    return _noindex(render_coming_soon(request, event, "teams", token=token))


@admin_required
def tonight(request):
    today = timezone.localdate()
    events = (
        Event.objects.filter(organization_id=request.user.organization_id, status=Event.Status.PUBLISHED)
        .prefetch_related("weeks")
        .order_by("name")
    )
    playing, upcoming = [], []
    for event in events:
        weeks = list(event.weeks.all())
        if week := tonight_week(weeks, today):
            playing.append((event, week))
        elif nxt := next_game_night(weeks, today):
            upcoming.append((nxt.date, event.name, event, nxt))
    if len(playing) == 1:
        event = playing[0][0]
        return redirect(reverse("event_schedule", args=[event.pk]) + "?view=tonight")
    next_night = None
    if not playing and upcoming:
        _, _, event, week = min(upcoming, key=lambda u: (u[0], u[1]))
        next_night = {"event": event, "week": week, "day": short_day(week.date)}
    return render(request, "league/tonight.html", {"playing": playing, "next_night": next_night})
