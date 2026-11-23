"""The league setup wizard: one frame, one view per step."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.permissions import admin_required

from .models import Event
from .setup import (
    STEP_LABELS,
    STEPS,
    SetupLocked,
    editing,
    first_open_step,
    mark_stale,
    set_weeks,
    step_done,
)
from .setup_forms import BasicsForm, ScoringForm


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
    "flights": placeholder_step,
    "teams": placeholder_step,
    "games": placeholder_step,
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
