from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Min
from django.shortcuts import render

from accounts.permissions import admin_required
from accounts.roles import player_for
from ui.nav import optional_reverse

from .display import date_range
from .models import Event, Team


@admin_required
def event_list(request):
    """P2 My Events: the admin's organization's events, newest first."""
    org_id = request.user.organization_id
    events = list(
        Event.objects.filter(organization_id=org_id)
        .annotate(
            first_date=Min("weeks__date"),
            last_date=Max("weeks__date"),
            flight_count=Count("divisions__flights", distinct=True),
        )
        .order_by(*Event._meta.ordering)
    ) if org_id else []
    for event in events:
        event.dates = date_range(event.first_date or event.start_date, event.last_date)
        page = "event_preview" if event.status == Event.Status.DRAFT else "event_schedule"
        event.link = optional_reverse(page, event.pk)
    return render(
        request,
        "league/event_list.html",
        {"events": events},
    )


@login_required
def my_games(request):
    """My Games (P11, first version): the player's teams in events that aren't drafts."""
    player = player_for(request.user)
    teams = []
    if player is not None:
        teams = list(
            Team.objects.filter(members__player=player)
            .exclude(flight__division__event__status=Event.Status.DRAFT)
            .select_related("flight__division__event")
            .order_by("-flight__division__event__start_date", "name")
        )
    return render(request, "league/my_games.html", {"teams": teams})
