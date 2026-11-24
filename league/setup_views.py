"""The league setup wizard: one frame, one view per step."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, RestrictedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
import scheduler
from django.views.decorators.http import require_POST
from django.utils.safestring import mark_safe

from accounts.permissions import admin_required
from ui.nav import optional_reverse

from .models import Event, Flight, Match, Player, Team
from .scheduling import generate_event
from .setup_preview import plan_views
from .setup import (
    active_teams,
    delete_team,
    refresh_grids,
    STEP_LABELS,
    STEPS,
    SetupLocked,
    editing,
    first_open_step,
    mark_stale,
    set_weeks,
    sync_flights,
    step_done,
)
from .setup_forms import (
    PLAN_OPTIONS,
    BasicsForm,
    FlightsForm,
    GamesForm,
    ScoringForm,
    TeamForm,
    player_text,
)


def setup_event(request, pk: int) -> Event:
    """The event, only if it is a league in the admin's organization."""
    return get_object_or_404(
        Event, pk=pk, organization=request.user.organization, type=Event.Type.LEAGUE
    )


def step_url(event: Event, step: str) -> str:
    return reverse("event_setup_step", args=[event.pk, step])


def destination(event: Event, step: str, nav: str) -> str:
    """Where a successful save goes, from the posted nav value."""
    index = STEPS.index(step)
    if nav.startswith("goto:") and nav[5:] in STEPS:
        return step_url(event, nav[5:])
    if nav == "back":
        return step_url(event, STEPS[index - 1]) if index else reverse("event_list")
    return step_url(event, STEPS[min(index + 1, len(STEPS) - 1)])


def stepper_items(event: Event | None, current: str) -> list[dict]:
    done = step_done(event) if event else {}
    return [
        {
            "number": i + 1,
            "label": STEP_LABELS[step],
            "state": "current" if step == current else ("done" if done.get(step) else "upcoming"),
            "value": f"goto:{step}" if event else None,
        }
        for i, step in enumerate(STEPS)
    ]


def frame_context(event: Event | None, step: str, **extra) -> dict:
    return {
        "event": event,
        "step": step,
        "step_label": STEP_LABELS[step],
        "step_number": STEPS.index(step) + 1,
        "step_count": len(STEPS),
        "steps": stepper_items(event, step),
        "new": event is None,
        "page_title": "Create league" if event is None else f"Edit league · {event.name}",
        **extra,
    }


def _persist_locked(event: Event, step: str, form, allowed: list[str]) -> None:
    """Scores exist: only the allowed fields are written, under the event row lock."""
    with transaction.atomic():
        row = Event.objects.select_for_update().get(pk=event.pk)
        for name in allowed:
            setattr(row, name, form.cleaned_data[name])
        row.setup_step = max(row.setup_step, STEPS.index(step) + 1)
        row.save(update_fields=[*allowed, "setup_step"])


def _error_text(exc: Exception) -> str:
    return exc.messages[0] if isinstance(exc, ValidationError) else str(exc)


def basics_step(request, event: Event | None, step: str = "basics"):
    template = "league/setup/basics.html"
    locked = bool(event and event.has_scores())
    if request.method != "POST":
        form = BasicsForm(instance=event, locked=locked)
        return render(request, template, frame_context(event, step, form=form, locked=locked))
    before = (event.start_date, event.courts, event.weeks.count()) if event else None
    title_name = event.name if event else None
    form = BasicsForm(request.POST, instance=event, locked=locked)
    if form.is_valid():
        try:
            if event is None:
                event = _create(request, form)
            elif locked:
                _persist_locked(event, step, form, ["name"])
            else:
                _save_basics(event, step, form, before)
        except (SetupLocked, ValidationError) as exc:
            messages.error(request, _error_text(exc))
        else:
            return redirect(destination(event, step, request.POST.get("nav", "next")))
    if event is not None and title_name is not None:
        event.name = title_name
    return render(request, template, frame_context(event, step, form=form, locked=locked))


def _create(request, form: BasicsForm) -> Event:
    with transaction.atomic():
        event = form.save(commit=False)
        event.organization = request.user.organization
        event.type = Event.Type.LEAGUE
        event.setup_step = 1
        event.save()
        set_weeks(event, form.cleaned_data["weeks"])
    return event


def _save_basics(event: Event, step: str, form: BasicsForm, before: tuple) -> None:
    with editing(event) as row:
        form.instance.setup_step = max(row.setup_step, STEPS.index(step) + 1)
        form.save()
        weeks = form.cleaned_data["weeks"]
        if (form.instance.start_date, weeks) != (before[0], before[2]):
            set_weeks(form.instance, weeks)
        if (form.instance.start_date, form.instance.courts, weeks) != before:
            mark_stale(form.instance)


def scoring_step(request, event: Event, step: str = "scoring"):
    template = "league/setup/scoring.html"
    locked = event.has_scores()
    if request.method != "POST":
        form = ScoringForm(instance=event, locked=locked)
        return render(request, template, frame_context(event, step, form=form, locked=locked))
    form = ScoringForm(request.POST, instance=event, locked=locked)
    if form.is_valid():
        try:
            if locked:
                _persist_locked(event, step, form, ["player_score_entry"])
            else:
                with editing(event) as row:
                    form.instance.setup_step = max(row.setup_step, STEPS.index(step) + 1)
                    form.save()
        except SetupLocked as exc:
            messages.error(request, str(exc))
        else:
            return redirect(destination(event, step, request.POST.get("nav", "next")))
    return render(request, template, frame_context(event, step, form=form, locked=locked))


def flights_step(request, event: Event, step: str = "flights"):
    template = "league/setup/flights.html"
    locked = event.has_scores()
    if request.method != "POST":
        form = FlightsForm(event=event, locked=locked)
        return render(request, template, frame_context(event, step, form=form, locked=locked))
    form = FlightsForm(request.POST, event=event, locked=locked)
    removing: list = []
    if form.is_valid():
        try:
            with editing(event) as row:
                removing = sync_flights(row, form.selected(), form.cleaned_data["confirm"])
                if not removing:
                    row.setup_step = max(row.setup_step, STEPS.index(step) + 1)
                    row.save(update_fields=["setup_step"])
        except SetupLocked:
            return redirect(destination(event, step, request.POST.get("nav", "next")))
        except RestrictedError:
            messages.error(
                request, "Some of those flights have games that can't be removed. Nothing was changed."
            )
        else:
            if not removing:
                return redirect(destination(event, step, request.POST.get("nav", "next")))
    # Flight names come from fixed choices (no user input), so marking them safe keeps the apostrophe literal.
    warnings = [
        mark_safe(f"Removing {flight} deletes its {n} {'team' if n == 1 else 'teams'}.")
        for flight in removing
        for n in [flight.teams.count()]
    ]
    return render(
        request,
        template,
        frame_context(
            event,
            step,
            form=form,
            locked=locked,
            warnings=warnings,
            nav=request.POST.get("nav", "next"),
        ),
    )


def _event_flights(event: Event) -> list[Flight]:
    return list(
        Flight.objects.filter(division__event=event)
        .select_related("division__event__organization")
        .order_by("division__pk", "pk")
    )


def _flight_notes(flight: Flight) -> list[str]:
    teams = list(active_teams(flight).prefetch_related("members"))
    notes = []
    if len(teams) < 2:
        notes.append(f"Add at least 2 teams to {flight.name} before generating.")
    notes += [
        f"{t.name} needs exactly 2 players before generating."
        for t in teams
        if len(t.members.all()) != 2
    ]
    return notes


def _team_of(flight: Flight, value) -> Team | None:
    """The flight's team for a posted or queried pk; junk means no team."""
    value = str(value or "")
    return flight.teams.filter(pk=int(value)).first() if value.isascii() and value.isdigit() else None


def _chosen_flight(request, flights: list[Flight]) -> Flight | None:
    wanted = request.POST.get("flight") or request.GET.get("flight") or ""
    return next((f for f in flights if str(f.pk) == wanted), flights[0] if flights else None)


def _player_options(event: Event, q: str = "", limit: int = 10) -> list[dict]:
    players = Player.objects.filter(organization=event.organization)
    if q:
        players = players.filter(Q(name__icontains=q) | Q(email__icontains=q))
    return [{"text": player_text(p)} for p in players.order_by("name", "pk")[:limit]]


def _team_context(request, event: Event, flight: Flight, form=None, team=None) -> dict:
    teams = list(active_teams(flight).prefetch_related("members__player"))
    if form is None:
        wanted = request.GET.get("edit") or ""
        team = next((t for t in teams if str(t.pk) == wanted), None)
        if team or request.GET.get("add"):
            form = TeamForm(flight=flight, team=team)
    return {
        "flight": flight,
        "teams": teams,
        "form": form,
        "editing_team": team,
        "player_options": _player_options(event, limit=50),
        "locked": event.has_scores(),
    }


def teams_step(request, event: Event, step: str = "teams"):
    template = "league/setup/teams.html"
    flights = _event_flights(event)
    flight = _chosen_flight(request, flights)
    htmx = bool(request.headers.get("HX-Request"))

    def page(**extra):
        context = {"flights": [], "has_flights": bool(flights), "oob": htmx}
        if flight is not None:
            context["flights"] = [
                {
                    "flight": f,
                    "count": active_teams(f).count(),
                    "notes": _flight_notes(f),
                    "current": f == flight,
                }
                for f in flights
            ]
            context.update(_team_context(request, event, flight, **extra))
        return frame_context(event, step, **context)

    if request.method != "POST":
        return render(request, template, page())
    typed = any((request.POST.get(f) or "").strip() for f in ("name", "player1", "player2"))
    nav_only = request.POST.get("action") != "save_team"
    if nav_only and not typed:
        try:
            with editing(event) as row:
                row.setup_step = max(row.setup_step, STEPS.index(step) + 1)
                row.save(update_fields=["setup_step"])
        except SetupLocked:
            pass  # Navigation is never blocked.
        return redirect(destination(event, step, request.POST.get("nav", "next")))
    if flight is None:
        return redirect(step_url(event, step))
    team = _team_of(flight, request.POST.get("team"))
    form = TeamForm(request.POST, flight=flight, team=team)
    if form.is_valid():
        try:
            with editing(event):
                form.save()
                mark_stale(event)
                refresh_grids(event)
        except SetupLocked as exc:
            if nav_only:
                return redirect(destination(event, step, request.POST.get("nav", "next")))
            messages.error(request, str(exc))
        else:
            if nav_only:
                try:
                    with editing(event) as row:
                        row.setup_step = max(row.setup_step, STEPS.index(step) + 1)
                        row.save(update_fields=["setup_step"])
                except SetupLocked:
                    pass
                return redirect(destination(event, step, request.POST.get("nav", "next")))
            if htmx:
                return render(request, "league/setup/_team_list.html", page())
            return redirect(f"{step_url(event, step)}?flight={flight.pk}")
    if htmx:
        response = render(request, "league/setup/_team_row.html", page(form=form, team=team))
        response["HX-Retarget"] = "#team-row-slot"
        response["HX-Reswap"] = "innerHTML"
        return response
    return render(request, template, page(form=form, team=team))


@admin_required
def event_team_row(request, pk):
    event = setup_event(request, pk)
    flight = _chosen_flight(request, _event_flights(event))
    if flight is None:
        raise Http404
    team = _team_of(flight, request.GET.get("team"))
    context = _team_context(
        request, event, flight, form=TeamForm(flight=flight, team=team), team=team
    )
    return render(
        request,
        "league/setup/_team_row.html",
        {"event": event, "oob": bool(request.headers.get("HX-Request")), **context},
    )


@admin_required
@require_POST
def event_team_delete(request, pk, team_pk):
    event = setup_event(request, pk)
    team = get_object_or_404(Team, pk=team_pk, flight__division__event=event)
    flight_pk = team.flight_id
    try:
        with editing(event):
            delete_team(team)
    except SetupLocked as exc:
        messages.error(request, str(exc))
    except RestrictedError:
        messages.error(request, f"{team.name} has games that can't be removed. Nothing was changed.")
    return redirect(f"{step_url(event, 'teams')}?flight={flight_pk}")


@admin_required
def player_search(request, pk):
    event = setup_event(request, pk)
    q = request.GET.get("q") or request.GET.get("player1") or request.GET.get("player2") or ""
    return render(
        request, "league/setup/_player_options.html", {"players": _player_options(event, q.strip())}
    )


def _cards(form: GamesForm, views, locked: bool) -> list[dict]:
    """Template data per flight: plan radios and week cells (typed values when the form is bound)."""
    by_flight = {v.flight.pk: v for v in views}
    cards = []
    for sub in form.forms:
        view = by_flight[sub.flight.pk]
        plan = sub["plan"].value() if form.bound else view.plan
        seed = view.grid or [1] * sub.weeks
        custom = plan == "custom"
        cells = []
        for week in range(1, sub.weeks + 1):
            name = f"{sub.prefix}-w{week}"
            if form.bound and custom and f"w{week}" in sub.fields:
                value, error = sub[f"w{week}"].value(), "; ".join(sub[f"w{week}"].errors)
            else:
                value, error = seed[week - 1] if week <= len(seed) else 1, ""
            shown = view.grid[week - 1] if week <= len(view.grid) else ""
            cells.append({
                "week": week, "name": name, "id": f"id_{name}", "value": value, "error": error,
                "shown": shown, "empty": week in view.empty_weeks,
            })
        cards.append({
            "view": view,
            "plan_name": sub["plan"].html_name,
            "options": [{"value": v, "label": label, "checked": v == plan} for v, label in PLAN_OPTIONS],
            "plan_errors": sub["plan"].errors,
            "cells": cells,
            "inputs": custom and not locked and view.blocker is None,
            "hidden": not locked and not (custom and view.blocker is None),
        })
    return cards


def _games_context(event: Event, form: GamesForm, step: str = "games", **extra) -> dict:
    locked = event.has_scores()
    views, error = plan_views(event, form.valid_overrides())
    return frame_context(
        event,
        step,
        form=form,
        locked=locked,
        cards=_cards(form, views, locked),
        dry_run_error=error,
        has_matches=Match.objects.filter(flight__division__event=event).exists(),
        **extra,
    )


def _save_games(event: Event, form: GamesForm) -> None:
    """Store each flight's plan and grid under the event lock. Raises SetupLocked."""
    with editing(event) as row:
        before = {f.flight.pk: list(f.flight.games_per_team_by_week) for f in form.forms}
        presets = False
        for sub in form.forms:
            plan, grid = sub.override()
            flight = sub.flight
            flight.games_plan = plan
            if plan == "custom":
                flight.games_per_team_by_week = grid
            else:
                presets = True
            flight.save(update_fields=["games_plan", "games_per_team_by_week"])
        if presets:
            refresh_grids(row)
        after = {
            f.pk: list(f.games_per_team_by_week)
            for f in Flight.objects.filter(division__event=row)
        }
        row.setup_step = max(row.setup_step, len(STEPS))
        row.save(update_fields=["setup_step"])
        if after != before:
            mark_stale(row)


def _locked_refusal(request, event: Event):
    messages.error(request, str(SetupLocked()))
    return redirect(step_url(event, "games"))


def games_step(request, event: Event, step: str = "games"):
    template = "league/setup/games.html"
    if request.method != "POST":
        return render(request, template, _games_context(event, GamesForm(event), step))
    nav = request.POST.get("nav", "stay")
    if event.has_scores():
        if nav == "back" or nav.startswith("goto:"):  # Navigation is never blocked.
            return redirect(destination(event, step, nav))
        return _locked_refusal(request, event)
    form = GamesForm(event, request.POST)
    if form.is_valid():
        try:
            _save_games(event, form)
        except SetupLocked as exc:
            messages.error(request, str(exc))
            return redirect(step_url(event, step))
        if nav == "back" or nav.startswith("goto:"):
            return redirect(destination(event, step, nav))
        return render(request, template, _games_context(event, GamesForm(event), step))
    return render(request, template, _games_context(event, form, step))


@admin_required
@require_POST
def event_games_preview(request, pk):
    event = setup_event(request, pk)
    form = GamesForm(event, None if event.has_scores() else request.POST)
    if not event.has_scores():
        form.is_valid()
    return render(request, "league/setup/_games_cards.html", _games_context(event, form))


@admin_required
@require_POST
def event_generate(request, pk):
    event = setup_event(request, pk)
    template = "league/setup/games.html"
    if event.has_scores():
        return _locked_refusal(request, event)
    form = GamesForm(event, request.POST)
    if not form.is_valid():
        return render(request, template, _games_context(event, form))
    has_matches = Match.objects.filter(flight__division__event=event).exists()
    if has_matches and request.POST.get("confirm") != "1":
        return render(request, template, _games_context(event, form, confirm_needed=True))
    try:
        _save_games(event, form)
    except SetupLocked as exc:
        messages.error(request, str(exc))
        return redirect(step_url(event, "games"))
    fresh = GamesForm(event)
    views, _ = plan_views(event)
    blocker = next((v.blocker for v in views if v.blocker), None)
    try:
        if blocker:
            raise scheduler.ScheduleError(blocker)
        schedule = generate_event(event)
    except scheduler.ScheduleError as exc:
        messages.error(request, str(exc))
        return render(request, template, _games_context(event, fresh))
    games = len(schedule.matches)
    weeks = event.weeks.count()
    messages.success(
        request,
        f"Schedule drafted · {games} {'game' if games == 1 else 'games'} over "
        f"{weeks} {'week' if weeks == 1 else 'weeks'}",
    )
    return redirect(optional_reverse("event_preview", event.pk) or reverse("event_list"))


def placeholder_step(request, event: Event, step: str):
    """Stand-in until the step is built: navigation works, nothing is saved."""
    if request.method == "POST":
        return redirect(destination(event, step, request.POST.get("nav", "next")))
    return render(
        request,
        "league/setup/placeholder.html",
        frame_context(event, step, locked=event.has_scores()),
    )


# Step name -> view(request, event, step). Later tasks replace the placeholders.
STEP_VIEWS = {
    "basics": basics_step,
    "scoring": scoring_step,
    "flights": flights_step,
    "teams": teams_step,
    "games": games_step,
}


@admin_required
def event_create(request):
    if request.user.organization_id is None:
        raise Http404
    return basics_step(request, None)


@admin_required
def event_setup(request, pk):
    event = setup_event(request, pk)
    return redirect(step_url(event, first_open_step(event)))


@admin_required
def event_setup_step(request, pk, step):
    event = setup_event(request, pk)
    view = STEP_VIEWS.get(step)
    if view is None:
        raise Http404
    return view(request, event, step)
