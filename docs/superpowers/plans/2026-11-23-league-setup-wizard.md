# Slice 2: League Setup Wizard (P3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the five-step league setup wizard (Basics, Scoring, Flights, Teams, Games plan) at `/events/new/` and `/events/<id>/setup/<step>/`. It saves a draft after every step, shows a live per-flight summary on step 5, and ends with a Generate button that saves a real draft schedule. It also enforces the A13 "no input changes once scores exist" guard.

**Architecture:** The rules live in two plain modules, kept apart from the views:
- `league/setup.py`: plan defaults, grid refresh, flight sync, team delete, the stale flag, step completion, and the edit lock.
- `league/setup_preview.py`: an event-wide dry run of the scheduler that produces each flight card's summary, notes, and blocker.

Views in `league/setup_views.py` and forms in `league/setup_forms.py` are thin wrappers over those modules. Each step is a normal Django form post. HTMX only swaps in partials: the team row, the player options, and the games cards.

**Tech Stack:** Python 3.13, Django 6.1, HTMX 2.0.11 (vendored; `base.html` already sends the CSRF header), Basecoat 1.1.0 + Tailwind via django-tailwind-cli 4.8.3, pytest 9 + pytest-django 4.14.

**Spec:** `docs/superpowers/specs/2026-11-23-league-setup-wizard-design.md`, with the PRD (`Pickleball League Manager — PRD, ERD & Scheduling Spec.md`) Flow A, §5 P3 and §8 A13, and the front-end spec `docs/superpowers/specs/2026-11-19-front-end-design-system-design.md` (stepper and form-field components).

## Global Constraints

- Run Python through the venv: `.venv/Scripts/python`. Tests: `.venv/Scripts/python -m pytest` from the repo root. The whole suite must pass after every task. After template changes, run `.venv/Scripts/python manage.py tailwind build` so new classes compile.
- Slice-1 rules still apply:
  - No raw hex colors in templates; use the token utilities.
  - Tailwind classes live only in templates or `frontend/stryde.css`.
  - Coral and Teal fills carry `text-ink`.
  - `<title>` is `<page> · Stryde`.
  - Components are `{% include "components/x.html" with … only %}`.
  - Reuse `form_field`, `form_errors`, `empty_state`, `error_state`, and toasts through `django.contrib.messages`.
- Every wizard view is `@admin_required`. The event is fetched with `organization=request.user.organization` and `type=Event.Type.LEAGUE`. Anything else is a 404, and that includes admins with no organization.
- Every step is a plain `<form method="post">` that works with no JavaScript. HTMX only enhances it.
- Weeks 1–20 and courts 1–20. Games per team in any week: a whole number from 0 to 20.
- **A13 (from project memory):** once `event.has_scores()`, no schedule input may change: weeks, start date, courts, scoring format, flights, teams, or games plan. Only `name` and `player_score_entry` stay editable. The check and the write happen inside `transaction.atomic()` with `select_for_update()` on the Event row.
- **From project memory:** `Match.team_a` / `team_b` / `winner` / `forfeited_by` and `TeamMember.player` are `on_delete=RESTRICT`. Catch `django.db.models.RestrictedError`, never `ProtectedError`, and show it as a message, never a 500.
- Generate stays Draft. No publish, no invites, no P4 in this slice. After Generate, redirect to `optional_reverse("event_preview", pk)`, or to `event_list` when that doesn't exist.
- Copy, verbatim:
  - "Pick at least one flight."
  - "Removing {flight} deletes its {n} team(s)."
  - "Add at least 2 teams to {flight} before generating."
  - "{team} needs exactly 2 players before generating."
  - "{n} teams: one team sits out each round, so each week one team plays 1 fewer. Byes rotate."
  - "Week {w}: each team plays {g} game(s). On {c} court(s) that takes {r} rounds."
  - "Scores have been entered, so the setup is locked. Individual games can still be moved."
  - "Scores have been entered, so the weeks can't change."
  - "You changed the setup since the schedule was made. Regenerate to apply it."
  - "Regenerating replaces the current draft schedule."
  - "Schedule drafted · {n} games over {w} weeks"
  - "Each team plays every other team:" with options "once", "twice", "custom"
- Pluralize "team/teams", "game/games", "court/courts", "week/weeks" (1 → singular).

**Corrections to the spec, decided while planning** (the plan follows these):
- `Flight.games_plan` gets a fourth stored value, `""`, meaning **auto**: not chosen yet, so it follows `default_plan`. The wizard creates flights with `""`. The **model default is `"custom"`, not `"once"`, because every existing row (seed data, factories, admin) holds a hand-set grid. Saving step 5 stores her explicit choice.
- A third new field, `Event.setup_step` (0–5, the highest step she has saved), drives the stepper's "done" state and the `/setup/` redirect. Basics and Scoring have no other way to tell "saved" from "untouched defaults". Existing events and `seed_demo` events get 5.
- "Highlight the padded weeks" becomes: in a custom grid, any week with 0 games is shown in amber as "No games this week". That covers padded weeks with no extra storage.

## Review Focus

1. **A draft tournament row on My Events** (the seed has one) must not link into `/setup/`, which 404s for tournaments. It stays plain text until P4 exists. (Task 4)
2. **Removing a flight, or deleting a team, after a draft schedule exists.** RESTRICT foreign keys must not raise. Other flights' matches stay, and the event is marked stale. (Tasks 2 and 6)
3. **Bad numbers posted to step 5 or its HTMX preview** (blank, `-1`, `x`, `21`) re-render the cards with an error under that field. Nothing is saved and nothing 500s. (Task 7)
4. **Team names that differ only in case** ("Dinkers" vs "dinkers") are rejected as duplicates in the flight. The database constraint is case-sensitive, so the form has to check. (Task 6)
5. **Other organizations' data:** another org's event id 404s on every wizard URL, including the generate URL, and the player search never returns another org's players. (Tasks 4 and 6)

## File Structure

| File | Responsibility |
| --- | --- |
| `league/models.py`, `league/migrations/0002_setup_wizard.py` | `Flight.games_plan`, `Event.schedule_stale`, `Event.setup_step`, `Event.has_scores()`, A13 guard and re-dating in `set_week_count` |
| `league/scheduling.py` | `_check_ready` uses `has_scores`; `generate_event` locks the row and clears `schedule_stale` |
| `league/management/commands/seed_demo.py` | Seeded events get `setup_step = 5` |
| `league/setup.py` | Wizard rules: plans, grids, flight sync, team delete, stale flag, step completion, edit lock |
| `league/setup_preview.py` | Event-wide dry run → `FlightPlanView` per flight |
| `league/setup_forms.py` | `BasicsForm`, `ScoringForm`, `FlightsForm`, `TeamForm`, `GamesForm` |
| `league/setup_views.py`, `league/urls.py`, `league/views.py` | Wizard views and routes; My Events row links |
| `templates/components/stepper.html` | Numbered step bar (done / current / upcoming) |
| `templates/league/setup/*.html` | `_frame.html`, `basics.html`, `scoring.html`, `flights.html`, `teams.html`, `_team_row.html`, `_player_options.html`, `games.html`, `_games_cards.html` |
| `tests/test_setup_models.py`, `test_setup_rules.py`, `test_setup_preview.py`, `test_setup_basics.py`, `test_setup_flights.py`, `test_setup_teams.py`, `test_setup_games.py` | One test file per task |

Shared test helpers go in `tests/factories.py`. Add `admin_of(org, email="a@example.com") -> User` (moved from `tests/test_my_events.py`, which then imports it) and `score(match) -> GameScore` (creates game 1, 11–5).

---

### Task 1: Model fields, `has_scores`, and the A13 guard on weeks

**Files:**
- Modify: `league/models.py`, `league/scheduling.py`, `league/management/commands/seed_demo.py`, `tests/factories.py`
- Create: `league/migrations/0002_setup_wizard.py`
- Test: `tests/test_setup_models.py`

**Interfaces:**
- Produces:
  - `Flight.Plan(TextChoices)`: `AUTO = "", "Not chosen"`, `ONCE = "once"`, `TWICE = "twice"`, `CUSTOM = "custom"`. `Flight.games_plan = CharField(max_length=6, choices=Plan.choices, blank=True, default="custom")`.
  - `Event.schedule_stale = BooleanField(default=False)` and `Event.setup_step = PositiveSmallIntegerField(default=0)`.
  - `Event.has_scores() -> bool`: true if any match of the event is `final`, has `forfeited_by`, or has a `GameScore`.
  - `Event.set_week_count(n)` now raises `ValidationError("Scores have been entered, so the weeks can't change.")` when `has_scores()`. It also re-dates **every** week to `start_date + 7·(number−1)` (one `bulk_update`).
  - `generate_event(event)` re-fetches the event with `select_for_update()` inside its transaction and sets `schedule_stale=False` on success.
  - Migration: adds the three fields, then `RunPython` sets `setup_step=5` on existing events. Existing flights keep `"custom"` through the default.

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_models.py`

```python
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from league.models import Event, Flight, GameScore, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, make_event

pytestmark = pytest.mark.django_db


def two_team_match(event):
    flight = add_flight(event, games=(1,) * event.weeks.count())
    a, b = add_team(flight, "A"), add_team(flight, "B")
    return Match.objects.create(flight=flight, week=event.weeks.get(number=1),
                                round_no=1, court_no=1, team_a=a, team_b=b)


def test_defaults():
    event = make_event()
    assert (event.schedule_stale, event.setup_step) == (False, 0)
    assert add_flight(event).games_plan == "custom"


def test_has_scores_game_score_final_and_forfeit():
    event = make_event(weeks=1)
    match = two_team_match(event)
    assert not event.has_scores()
    GameScore.objects.create(match=match, game_no=1, points_a=11, points_b=5)
    assert event.has_scores()
    match.games.all().delete(); match.status = "final"; match.save()
    assert event.has_scores()
    match.status = "scheduled"; match.forfeited_by = match.team_a; match.save()
    assert event.has_scores()


def test_set_week_count_redates_every_week():
    event = make_event(weeks=2)                      # starts 2027-03-02
    event.start_date = date(2027, 3, 9); event.save()
    event.set_week_count(3)
    assert [w.date for w in event.weeks.all()] == [date(2027, 3, 9), date(2027, 3, 16), date(2027, 3, 23)]


def test_set_week_count_blocked_once_scored():
    event = make_event(weeks=1)
    GameScore.objects.create(match=two_team_match(event), game_no=1, points_a=11, points_b=5)
    with pytest.raises(ValidationError, match="Scores have been entered, so the weeks can't change."):
        event.set_week_count(2)


def test_generate_clears_stale():
    event = make_event(weeks=1)
    two_team_match(event).delete()
    Event.objects.filter(pk=event.pk).update(schedule_stale=True)
    generate_event(event)
    event.refresh_from_db()
    assert event.schedule_stale is False and Match.objects.filter(flight__division__event=event).count() == 1


def test_seed_events_are_fully_set_up():
    call_command("seed_demo")
    assert set(Event.objects.values_list("setup_step", flat=True)) == {5}
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_models.py -v` FAIL (missing fields).

- [ ] **Step 3: Implement** the fields, the migration (`makemigrations league --name setup_wizard`, then add the `RunPython`), `has_scores`, and the `set_week_count` changes. Replace the inline scored query in `_check_ready` with `event.has_scores()`; its message is unchanged. Add the lock and the stale reset to `generate_event`. Set `setup_step=5` on both events in `seed_demo`. Add `admin_of` and `score` to `tests/factories.py`, and switch `tests/test_my_events.py` to import `admin_of`.

- [ ] **Step 4: Run the tests** → the new file PASSES, then the full suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add league tests
git commit -m "feat(league): setup fields, has_scores, and the A13 guard on week count"
```

---

### Task 2: Wizard rules (`league/setup.py`)

**Files:**
- Create: `league/setup.py`
- Test: `tests/test_setup_rules.py`

**Interfaces:**
- Consumes: Task 1 fields, `scheduler.round_robin_preset`, `scheduler.ScheduleError`.
- Produces (all in `league/setup.py`):
  - `STEPS: tuple[str, ...] = ("basics", "scoring", "flights", "teams", "games")` and `STEP_LABELS = {"basics": "Basics", "scoring": "Scoring", "flights": "Flights", "teams": "Teams", "games": "Games plan"}`.
  - `class SetupLocked(Exception)`, whose message is the A13 banner copy.
  - `active_teams(flight) -> QuerySet[Team]`: the flight's teams with `withdrawn_at__isnull=True`, ordered by `pk`.
  - `default_plan(n_teams: int, weeks: int) -> str`: the first of `"once"` / `"twice"` whose total games per team (`times × (n−1)` if n is even, else `times × n`) is `>= weeks`. Returns `"custom"` if neither fits, and `"once"` when `n_teams < 2`.
  - `effective_plan(flight, n_teams: int, weeks: int) -> str`: `flight.games_plan or default_plan(n_teams, weeks)`.
  - `plan_grid(plan: str, n_teams: int, weeks: int, stored: list[int]) -> list[int]`: once/twice → `list(round_robin_preset(n, weeks, 1|2))`, or `[]` on `ScheduleError` or when `n < 2`. Custom → `stored` cut or padded with `0` to `weeks` entries. If the plan is auto-resolved to custom and `stored` is empty → `[1] * weeks`.
  - `refresh_grids(event) -> None`: recomputes and saves `games_per_team_by_week` for every flight with `plan_grid(effective_plan(...), ...)`. It never raises.
  - `set_weeks(event, n: int) -> None`: `event.set_week_count(n)`, then `refresh_grids(event)`.
  - `sync_flights(event, cells: set[tuple[str, str]], confirm: bool) -> list[Flight]`: `cells` is a set of `(level, format)`.
    - Without `confirm`, if any flight to remove has teams, it changes nothing and returns those flights.
    - Otherwise it creates the missing Divisions and Flights (`games_plan=""`), deletes the removed flights and any Divisions left empty, calls `mark_stale(event)` if anything was removed, and returns `[]`.
  - `delete_team(team) -> None`: in one transaction, deletes all `Match` rows of `team.flight`, then the team. Then `mark_stale(team.flight.event)` and `refresh_grids(event)`.
  - `mark_stale(event) -> None`: sets `schedule_stale=True` only if the event has matches.
  - `step_done(event) -> dict[str, bool]`: per step, `setup_step >= index+1` and also:
    - flights: at least 1 flight exists;
    - teams: every flight has at least 2 active teams and each active team has 2 members;
    - games: every flight's grid length equals the week count.
  - `first_open_step(event) -> str`: the first step not done, else `"games"`.
  - `@contextmanager editing(event) -> Iterator[Event]`: opens `transaction.atomic()`, re-fetches the event with `select_for_update()`, and raises `SetupLocked` if `has_scores()`. Otherwise it yields the locked event.

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_rules.py`

```python
import pytest

from league.models import Division, Flight, Match
from league.scheduling import generate_event
from league.setup import (SetupLocked, default_plan, delete_team, editing, refresh_grids,
                          set_weeks, step_done, sync_flights)
from tests.factories import add_flight, add_team, make_event, score

pytestmark = pytest.mark.django_db


def auto_flight(event, n, format="mens"):
    flight = add_flight(event, format=format, games=())
    flight.games_plan = ""; flight.save()
    for i in range(n):
        add_team(flight, f"{format}{i}")
    refresh_grids(event); flight.refresh_from_db()
    return flight


def test_default_plan():
    assert default_plan(4, 3) == "once"
    assert default_plan(4, 4) == "twice"
    assert default_plan(4, 7) == "custom"
    assert default_plan(5, 5) == "once"
    assert default_plan(1, 4) == "once"


def test_auto_flight_demo_size_is_twice():
    assert auto_flight(make_event(weeks=4), 4).games_per_team_by_week == [2, 2, 1, 1]


def test_preset_that_does_not_fit_stores_empty_grid():
    event = make_event(weeks=4)
    flight = auto_flight(event, 4)
    flight.games_plan = "once"; flight.save()
    refresh_grids(event); flight.refresh_from_db()
    assert flight.games_per_team_by_week == []


def test_custom_grid_cut_and_padded():
    event = make_event(weeks=4)
    flight = add_flight(event, games=(2, 3, 1, 2))       # games_plan "custom"
    set_weeks(event, 2); flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 3]
    set_weeks(event, 4); flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 3, 0, 0]


def test_withdrawn_teams_not_counted():
    from django.utils import timezone
    event = make_event(weeks=4)
    flight = auto_flight(event, 5)
    flight.teams.filter(name="mens4").update(withdrawn_at=timezone.now())
    refresh_grids(event); flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 2, 1, 1]  # 4 active teams → twice


def test_sync_flights_add_then_confirm_remove():
    event = make_event()
    assert sync_flights(event, {("intermediate", "mens"), ("advanced", "mixed")}, confirm=False) == []
    assert {f.games_plan for f in Flight.objects.filter(division__event=event)} == {""}
    mens = Flight.objects.get(division__event=event, format="mens")
    add_team(mens, "A")
    pending = sync_flights(event, {("advanced", "mixed")}, confirm=False)
    assert [f.name for f in pending] == ["Intermediate Men's"]
    assert Flight.objects.filter(pk=mens.pk).exists()
    assert sync_flights(event, {("advanced", "mixed")}, confirm=True) == []
    assert not Division.objects.filter(event=event, level="intermediate").exists()


def test_removing_scheduled_flight_keeps_other_flights_matches():
    event = make_event(weeks=1)
    mens, mixed = auto_flight(event, 2, "mens"), auto_flight(event, 2, "mixed")
    generate_event(event)
    sync_flights(event, {("intermediate", "mixed")}, confirm=True)
    event.refresh_from_db()
    assert event.schedule_stale is True
    assert set(Match.objects.filter(flight__division__event=event).values_list("flight", flat=True)) == {mixed.pk}


def test_delete_team_with_draft_schedule():
    event = make_event(weeks=1)
    mens, mixed = auto_flight(event, 3, "mens"), auto_flight(event, 2, "mixed")
    generate_event(event)
    delete_team(mens.teams.first())
    event.refresh_from_db()
    assert event.schedule_stale is True
    assert not Match.objects.filter(flight=mens).exists() and Match.objects.filter(flight=mixed).exists()


def test_step_done():
    event = make_event(weeks=4)
    event.setup_step = 5; event.save()
    assert step_done(event) == {"basics": True, "scoring": True, "flights": False, "teams": False, "games": False}
    auto_flight(event, 4)
    assert all(step_done(event).values())


def test_editing_locks_once_scored():
    event = make_event(weeks=1)
    auto_flight(event, 2)
    generate_event(event)
    with editing(event) as locked:
        assert locked.pk == event.pk
    score(Match.objects.first())
    with pytest.raises(SetupLocked):
        with editing(event):
            pass
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_rules.py -v` FAIL (no module).

- [ ] **Step 3: Implement** `league/setup.py` as specified. In `delete_team` and `sync_flights`, wrap the deletes in `transaction.atomic()`. Catch `RestrictedError` only in views (Tasks 5 and 6); here it propagates.

- [ ] **Step 4: Run the tests** → PASS, then the full suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add league/setup.py tests/test_setup_rules.py
git commit -m "feat(league): wizard rules for plans, grids, flights, teams and the edit lock"
```

---

### Task 3: Games-plan preview (`league/setup_preview.py`)

**Files:**
- Create: `league/setup_preview.py`
- Test: `tests/test_setup_preview.py`

**Interfaces:**
- Consumes: `active_teams`, `effective_plan`, `plan_grid` (Task 2); `league.scheduling.event_flights`; `scheduler.generate`, `fairness_report`, `summary_line`, `ScheduleError`.
- Produces:
  - `@dataclass(frozen=True) FlightPlanView` with fields:
    - `flight: Flight`, `team_count: int`, `plan: str` (resolved, never `""`), `grid: list[int]`, `total: int`
    - `summary: str | None`
    - `notes: list[str]`: odd-team note first, then long-night notes in week order
    - `blocker: str | None`: blocks Generate
    - `empty_weeks: list[int]`: 1-based weeks with 0 games, custom plans only
  - `plan_views(event, overrides: dict[int, tuple[str, list[int]]] | None = None) -> tuple[list[FlightPlanView], str | None]`. `overrides` maps a flight pk to `(plan, custom grid)`, for unsaved form values. Nothing is written to the DB. The second value is the scheduler's own `ScheduleError` text from the dry run, or `None`.
  - Blocker order per flight:
    1. Fewer than 2 active teams → "Add at least 2 teams to {flight} before generating."
    2. A team without exactly 2 members → "{team} needs exactly 2 players before generating."
    3. An empty once/twice grid → the `round_robin_preset` message.
  - Flights with a blocker are left out of the dry run and get `summary=None`.
  - Dry run: `event_flights(event)`, replace each grid with the view's grid (`dataclasses.replace`), drop blocked flights, then `generate(..., event.courts)` and `fairness_report`.
  - Long night: for each week, `rounds` = the highest `round_no` among **all** matches that week (every flight). `g` = the most games any team of this flight plays that week. Add a note when `g > 0 and rounds > g`.

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_preview.py`

```python
import pytest

from league.models import Flight
from league.setup import refresh_grids
from league.setup_preview import plan_views
from tests.factories import add_flight, add_team, make_event

pytestmark = pytest.mark.django_db


def flight_with(event, n, games, plan="custom", format="mens"):
    flight = add_flight(event, format=format, games=games)
    flight.games_plan = plan; flight.save()
    for i in range(n):
        add_team(flight, f"{format}{i}")
    refresh_grids(event); flight.refresh_from_db()
    return flight


def test_summary_for_custom_grid():
    event = make_event(weeks=4, courts=2)
    flight_with(event, 4, (1, 1, 1, 1))
    (view,), error = plan_views(event)
    assert error is None and view.blocker is None and view.total == 4
    assert view.summary == "8 games · 4 per team · every pair meets 1–2 times"


def test_odd_team_note_and_preset_grid():
    event = make_event(weeks=4, courts=2)
    flight_with(event, 5, (), plan="")
    (view,), _ = plan_views(event)
    assert view.plan == "once" and view.grid == [2, 1, 1, 1]
    assert view.notes[0] == "5 teams: one team sits out each round, so each week one team plays 1 fewer. Byes rotate."


def test_long_night_counts_every_flight_on_the_courts():
    event = make_event(weeks=1, courts=2)
    flight_with(event, 4, (1,), format="mens")
    flight_with(event, 4, (1,), format="mixed")
    views, _ = plan_views(event)
    for view in views:
        assert view.notes == ["Week 1: each team plays 1 game. On 2 courts that takes 2 rounds."]


def test_blockers():
    event = make_event(weeks=4)
    flight_with(event, 1, (1, 1, 1, 1))
    (view,), _ = plan_views(event)
    assert view.blocker == "Add at least 2 teams to Intermediate Men's before generating." and view.summary is None
    flight = Flight.objects.get()
    flight.teams.first().members.first().delete()
    add_team(flight, "Second")
    (view,), _ = plan_views(event)
    assert view.blocker == "mens0 needs exactly 2 players before generating."


def test_preset_error_blocks():
    event = make_event(weeks=4)
    flight_with(event, 4, (), plan="once")
    (view,), _ = plan_views(event)
    assert view.blocker == ("Round robin once is 3 games per team, but you have 4 weeks. "
                            "Week 4 has no games — reduce weeks or choose twice.")


def test_overrides_are_not_saved_and_zero_weeks_flagged():
    event = make_event(weeks=4)
    flight = flight_with(event, 4, (1, 1, 1, 1))
    (view,), _ = plan_views(event, {flight.pk: ("custom", [2, 2, 0, 0])})
    assert view.grid == [2, 2, 0, 0] and view.empty_weeks == [3, 4]
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [1, 1, 1, 1]
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_preview.py -v` FAIL.

- [ ] **Step 3: Implement** `league/setup_preview.py` as specified.

- [ ] **Step 4: Run the tests** → PASS, then the full suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add league/setup_preview.py tests/test_setup_preview.py
git commit -m "feat(league): event-wide games-plan preview with summary, notes and blockers"
```

---

### Task 4: Wizard frame, stepper, Basics and Scoring

**Files:**
- Create: `league/setup_forms.py`, `league/setup_views.py`, `templates/components/stepper.html`, `templates/league/setup/_frame.html`, `basics.html`, `scoring.html`
- Modify: `league/urls.py`, `league/views.py` (row links), `frontend/stryde.css` (stepper styles if needed)
- Test: `tests/test_setup_basics.py`

**Interfaces:**
- Consumes: `STEPS`, `STEP_LABELS`, `step_done`, `first_open_step`, `editing`, `SetupLocked`, `set_weeks`, `mark_stale` (Task 2).
- Produces:
  - URLs (in `league/urls.py`):
    - `events/new/` → `event_create`
    - `events/<int:pk>/setup/` → `event_setup` (redirects to `first_open_step`)
    - `events/<int:pk>/setup/<str:step>/` → `event_setup_step`, which dispatches to one view per step. An unknown step is a 404.
    - Later tasks add `event_games_preview`, `event_generate`, `event_team_row`, `event_team_delete`, and `player_search`.
  - `setup_event(request, pk) -> Event` in `setup_views.py`: the org + league scoped `get_object_or_404`.
  - Navigation: every step form posts a `nav` value: `next`, `back`, or `goto:<step>`. After a successful save the view sets `setup_step = max(setup_step, index+1)` and redirects:
    - `next` → the following step;
    - `back` → the previous step;
    - `goto:<step>` → that step.
  - Stepper items are `<button name="nav" value="goto:<step>" form="step-form">` once the event exists, so clicking a step saves the current one first. On `/events/new/` they're plain text.
  - `components/stepper.html` takes `steps`: a list of `{"number", "label", "state": "done"|"current"|"upcoming", "value"}`, plus `form_id`. Each item has `data-state="<state>"`. Below `md` it collapses to "Step {n} of 5 · {label}".
  - `_frame.html` blocks: `step_body` and `step_footer`. It shows the A13 banner when `locked`, and the stale banner when `event.schedule_stale`.
  - `BasicsForm(ModelForm)`: fields `name`, `start_date` (date input), `courts` (1–20), plus `weeks = IntegerField(min 1, max 20)`. `locked=True` sets `disabled` on all but `name`.
  - `ScoringForm(ModelForm)`: fields `match_format`, `points_to_win`, `win_by_two`, `player_score_entry`. `locked=True` disables all but `player_score_entry`.
  - Saving Basics calls `set_weeks` when weeks or start date change, and `mark_stale` when weeks, start date or courts change. Saving Scoring never marks stale.
  - Basics and Scoring save through `transaction.atomic()` + `select_for_update()` even when locked. The disabled fields keep the stored values, which is how only `name` / `player_score_entry` can change.
  - My Events row link (`league/views.py`):
    - draft league with matches → `optional_reverse("event_preview", pk)` or `reverse("event_setup", args=[pk])`;
    - draft league without matches → `event_setup`;
    - draft tournament → `optional_reverse("event_preview", pk)`;
    - not a draft → unchanged.
  - Page titles: "Create league" on `/events/new/`, "Edit league · {name}" afterwards. Footer buttons: Back (on step 1 of a new event it's a "Cancel" link to `event_list`) and Next.

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_basics.py`

```python
from datetime import date

import pytest

from accounts.models import Organization, User
from league.models import Event, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db
BASICS = {"name": "Fall League", "start_date": "2027-09-07", "weeks": "4", "courts": "2", "nav": "next"}


@pytest.fixture
def admin(client):
    user = admin_of(Organization.objects.get_or_create(name="Waco Regional")[0])
    client.force_login(user)
    return user


def test_create_league(client, admin):
    page = client.get("/events/new/").content.decode()
    assert "Create league" in page and "Basics" in page
    response = client.post("/events/new/", BASICS)
    event = Event.objects.get(name="Fall League")
    assert response.url == f"/events/{event.pk}/setup/scoring/"
    assert (event.type, event.status, event.setup_step, event.organization) == ("league", "draft", 1, admin.organization)
    assert [w.date for w in event.weeks.all()][-1] == date(2027, 9, 28)


def test_basics_validation(client, admin):
    response = client.post("/events/new/", {**BASICS, "weeks": "21"})
    assert response.status_code == 200 and not Event.objects.exists()


def test_scoring_and_back(client, admin):
    event = make_event()
    response = client.post(f"/events/{event.pk}/setup/scoring/",
                           {"match_format": "best_of_3", "points_to_win": "15", "win_by_two": "on", "nav": "back"})
    event.refresh_from_db()
    assert response.url == f"/events/{event.pk}/setup/basics/"
    assert (event.match_format, event.points_to_win, event.setup_step) == ("best_of_3", 15, 2)


def test_stepper_goto_saves_first(client, admin):
    event = make_event()
    client.post(f"/events/{event.pk}/setup/basics/", {**BASICS, "nav": "goto:flights"})
    event.refresh_from_db()
    assert event.name == "Fall League"


def test_setup_redirects_to_first_open_step(client, admin):
    event = make_event(); event.setup_step = 2; event.save()
    assert client.get(f"/events/{event.pk}/setup/").url == f"/events/{event.pk}/setup/flights/"


def test_access(client, admin):
    other = make_event(); Event.objects.filter(pk=other.pk).update(
        organization=Organization.objects.create(name="Other"))
    cup = make_event(name="Cup", type="tournament", window_minutes=120)
    assert client.get(f"/events/{other.pk}/setup/basics/").status_code == 404
    assert client.get(f"/events/{cup.pk}/setup/basics/").status_code == 404
    assert client.get(f"/events/{cup.pk}/setup/nonsense/").status_code == 404
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=admin.organization))
    assert client.get("/events/new/").status_code == 403


def test_weeks_change_marks_stale(client, admin):
    event = make_event(weeks=1)
    flight = add_flight(event, games=(1,)); add_team(flight, "A"); add_team(flight, "B")
    generate_event(event)
    client.post(f"/events/{event.pk}/setup/basics/", {**BASICS, "weeks": "2"})
    event.refresh_from_db()
    assert event.weeks.count() == 2 and event.schedule_stale is True


def test_locked_basics_only_name_changes(client, admin):
    event = make_event(weeks=1, courts=2)
    flight = add_flight(event, games=(1,)); add_team(flight, "A"); add_team(flight, "B")
    generate_event(event); score(Match.objects.get())
    page = client.get(f"/events/{event.pk}/setup/basics/").content.decode()
    assert "Scores have been entered, so the setup is locked. Individual games can still be moved." in page
    client.post(f"/events/{event.pk}/setup/basics/", {**BASICS, "courts": "5", "weeks": "3"})
    event.refresh_from_db()
    assert (event.name, event.courts, event.weeks.count()) == ("Fall League", 2, 1)


def test_my_events_links(client, admin):
    league = make_event()
    make_event(name="Cup", type="tournament", window_minutes=120)
    html = client.get("/events/").content.decode()
    assert f'href="/events/{league.pk}/setup/"' in html
    assert "/setup/" not in html.replace(f"/events/{league.pk}/setup/", "")   # tournament row has no setup link
```

`make_event` creates its org as "Waco Regional", the same org as the `admin` fixture.

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_basics.py -v` FAIL.

- [ ] **Step 3: Implement** the forms, the views, the URLs, the stepper component, the frame and the two step templates, and the My Events link rule, as specified. Use `form_field` for every input.

- [ ] **Step 4: Run the tests** → PASS, then the full suite PASSES (`test_my_events.py` included).

- [ ] **Step 5: Commit**

```bash
git add league templates frontend tests/test_setup_basics.py
git commit -m "feat(league): setup wizard frame and stepper with Basics and Scoring steps"
```

---

### Task 5: Flights step

**Files:**
- Modify: `league/setup_forms.py`, `league/setup_views.py`
- Create: `templates/league/setup/flights.html`
- Test: `tests/test_setup_flights.py`

**Interfaces:**
- Consumes: `sync_flights`, `editing`, `SetupLocked` (Task 2); the frame (Task 4).
- Produces:
  - `FlightsForm` with `cells = MultipleChoiceField(widget=CheckboxSelectMultiple)`. The choices are `"<level>:<format>"` for the 3 levels × 3 formats, in Division.Level and Flight.Format order. It has a hidden `confirm` BooleanField, and an empty selection fails with "Pick at least one flight."
  - The page is a 3×3 table: rows Beginner / Intermediate / Advanced, columns Men's / Women's / Mixed, with one checkbox per cell. Existing flights are pre-ticked.
  - When `sync_flights(..., confirm=False)` returns flights, the view re-renders with a warning panel. The panel has one line per flight, "Removing {flight} deletes its {n} team(s).", a "Remove and continue" button (`confirm=1`, same `nav`), and a "Keep them" button that reloads the step.
  - Every POST runs inside `editing(event)`. On `SetupLocked`, it adds the message and redirects to the same step. The GET renders the grid disabled.
  - A `RestrictedError` from the delete is caught, shown as an error message, and the step re-renders.

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_flights.py`

```python
import pytest

from accounts.models import Organization
from league.models import Flight, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db


@pytest.fixture
def event(client):
    event = make_event()
    client.force_login(admin_of(event.organization))
    return event


def url(event):
    return f"/events/{event.pk}/setup/flights/"


def test_grid_and_save(client, event):
    html = client.get(url(event)).content.decode()
    assert html.count('name="cells"') == 9
    response = client.post(url(event), {"cells": ["intermediate:mens", "advanced:mixed"], "nav": "next"})
    assert response.url == f"/events/{event.pk}/setup/teams/"
    assert sorted(f.name for f in Flight.objects.filter(division__event=event)) == ["Advanced Mixed", "Intermediate Men's"]
    event.refresh_from_db()
    assert event.setup_step == 3


def test_none_ticked(client, event):
    assert "Pick at least one flight." in client.post(url(event), {"nav": "next"}).content.decode()


def test_remove_flight_with_teams_needs_confirm(client, event):
    flight = add_flight(event, format="mens")
    add_team(flight, "A"); add_team(flight, "B")
    html = client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next"}).content.decode()
    assert "Removing Intermediate Men's deletes its 2 teams." in html
    assert Flight.objects.filter(pk=flight.pk).exists()
    client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next", "confirm": "1"})
    assert not Flight.objects.filter(pk=flight.pk).exists()


def test_locked(client, event):
    flight = add_flight(event, games=(1, 1, 1, 1))
    add_team(flight, "A"); add_team(flight, "B")
    generate_event(event); score(Match.objects.first())
    response = client.post(url(event), {"cells": ["advanced:mixed"], "nav": "next"}, follow=True)
    assert "Scores have been entered, so the setup is locked." in response.content.decode()
    assert Flight.objects.filter(pk=flight.pk).exists()
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_flights.py -v` FAIL.

- [ ] **Step 3: Implement** as specified.

- [ ] **Step 4: Run the tests** → PASS, then the full suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add league templates tests/test_setup_flights.py
git commit -m "feat(league): Flights step with the level × format grid and confirm-to-remove"
```

---

### Task 6: Teams step and player type-ahead

**Files:**
- Modify: `league/setup_forms.py`, `league/setup_views.py`, `league/urls.py`
- Create: `templates/league/setup/teams.html`, `_team_row.html`, `_player_options.html`
- Test: `tests/test_setup_teams.py`

**Interfaces:**
- Consumes: `active_teams`, `delete_team`, `mark_stale`, `refresh_grids`, `editing` (Task 2); the frame (Task 4).
- Produces:
  - URLs:
    - `events/<pk>/setup/teams/row/` → `event_team_row` (GET; `?flight=<pk>&team=<pk?>`). It returns `_team_row.html`, the inline add/edit row.
    - `events/<pk>/setup/teams/<int:team_pk>/delete/` → `event_team_delete` (POST).
    - `events/<pk>/setup/teams/players/` → `player_search` (GET `?q=`). It returns `_player_options.html`: up to 10 `<option>`s from the admin's org, matched with `icontains` on name or email and ordered by name.
  - The page `/setup/teams/?flight=<pk>` defaults to the first flight (by division pk, pk). The left column links to each flight with its team count. With no flights it shows the empty state "Add a flight first." with a link to the Flights step.
  - **Player text format.** An option's value, which is also what a player field accepts, is `"Name <email>"` when the player has an email and `"Name (#pk)"` otherwise. The `<datalist>` is pre-filled with up to 50 org players, and HTMX (`hx-get` to `player_search`, `hx-trigger="input changed delay:250ms"`) refreshes it as she types.
  - `TeamForm(flight, team=None)`: fields `name`, `player1`, `player1_email`, `player2`, `player2_email` (emails optional, only for new players), and hidden `team` (pk when editing). `clean()` resolves each player slot to an existing `Player` or a new one to create. Errors, verbatim:
    - name clash, case-insensitive, among the flight's other teams → "There's already a team called {existing name} in this flight."
    - a plain name that matches two or more org players → "Two players are named {name}. Pick one from the list."
    - a new player whose email is already used in the org → "{Name} <{email}> already uses that email. Pick them from the list."
    - both slots are the same player → "Pick two different players."
    - a player already on another active team in this flight → "{player} is already on {team} in this flight."
    - Resolution order: `(#pk)` suffix → `<email>` suffix (case-insensitive) → a single exact name match (case-insensitive) when that slot's email field is empty → otherwise a new player.
  - `TeamForm.save() -> Team` creates any new players, then the team and its two `TeamMember`s, or updates the name and members of an existing team.
  - The POST to the step URL with `action=save_team` saves the team inside `editing(event)`. It then calls `mark_stale(event)` and `refresh_grids(event)` and redirects to `?flight=<pk>`. An HTMX request gets the updated team list partial instead. A POST with `nav` just navigates and sets `setup_step >= 4`, never blocked.
  - Amber notes under each flight, from `plan_views`' blockers or direct checks: "Add at least 2 teams to {flight} before generating." and "{team} needs exactly 2 players before generating."
  - Delete posts through `delete_team` inside `editing(event)`. It catches `RestrictedError` and shows it as an error message.

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_teams.py`

```python
import pytest

from accounts.models import Organization
from league.models import Match, Player, Team
from league.scheduling import generate_event
from tests.factories import add_flight, add_player, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(client):
    event = make_event(weeks=4)
    flight = add_flight(event, games=())
    flight.games_plan = ""; flight.save()
    client.force_login(admin_of(event.organization))
    return event, flight


def post_team(client, event, flight, **fields):
    data = {"action": "save_team", "flight": flight.pk, "name": "Dinkers",
            "player1": "Sam Lee", "player1_email": "sam@example.com",
            "player2": "Pat Kim <pat@example.com>", "player2_email": ""}
    data.update(fields)
    return client.post(f"/events/{event.pk}/setup/teams/?flight={flight.pk}", data)


def test_add_team_with_new_and_existing_player(client, setup):
    event, flight = setup
    pat = add_player(event.organization, "Pat Kim", "pat@example.com")
    assert post_team(client, event, flight).status_code == 302
    team = Team.objects.get(name="Dinkers")
    assert set(team.players.values_list("name", flat=True)) == {"Sam Lee", "Pat Kim"}
    assert Player.objects.filter(name="Pat Kim").count() == 1 and team.players.filter(pk=pat.pk).exists()


@pytest.mark.parametrize("fields, message", [
    ({"name": "dinkers"}, "There's already a team called Dinkers in this flight."),
    ({"name": "Smashers", "player1": "Ann Cho <ann@example.com>", "player1_email": "",
      "player2": "Ann Cho <ann@example.com>"}, "Pick two different players."),
    ({"name": "Smashers", "player1": "Ann Cho", "player1_email": "pat@example.com"},
     "Pat Kim <pat@example.com> already uses that email. Pick them from the list."),
])
def test_team_validation(client, setup, fields, message):
    event, flight = setup
    add_player(event.organization, "Pat Kim", "pat@example.com")
    add_player(event.organization, "Ann Cho", "ann@example.com")
    post_team(client, event, flight)
    assert message in post_team(client, event, flight, **fields).content.decode()


def test_player_already_on_team_in_flight(client, setup):
    event, flight = setup
    add_player(event.organization, "Pat Kim", "pat@example.com")
    post_team(client, event, flight)
    html = post_team(client, event, flight, name="Smashers", player1="Ann Cho", player1_email="").content.decode()
    assert "Pat Kim is already on Dinkers in this flight." in html


def test_ambiguous_name(client, setup):
    event, flight = setup
    add_player(event.organization, "Sam Lee"); add_player(event.organization, "Sam Lee")
    html = post_team(client, event, flight, player1_email="").content.decode()
    assert "Two players are named Sam Lee. Pick one from the list." in html


def test_adding_teams_refreshes_auto_grid(client, setup):
    event, flight = setup
    for i in range(4):
        post_team(client, event, flight, name=f"T{i}", player1=f"P{i}a", player1_email="",
                  player2=f"P{i}b")
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 2, 1, 1]


def test_delete_team_after_generate(client, setup):
    event, flight = setup
    flight.games_plan = "custom"; flight.games_per_team_by_week = [1, 1, 1, 1]; flight.save()
    teams = [add_team(flight, n) for n in "ABC"]
    generate_event(event)
    client.post(f"/events/{event.pk}/setup/teams/{teams[0].pk}/delete/")
    event.refresh_from_db()
    assert not Team.objects.filter(pk=teams[0].pk).exists()
    assert not Match.objects.filter(flight=flight).exists() and event.schedule_stale


def test_player_search_is_org_scoped(client, setup):
    event, _ = setup
    add_player(event.organization, "Sam Lee", "sam@example.com")
    add_player(Organization.objects.create(name="Other"), "Sam Other", "so@example.com")
    html = client.get(f"/events/{event.pk}/setup/teams/players/?q=sam").content.decode()
    assert 'value="Sam Lee &lt;sam@example.com&gt;"' in html and "Sam Other" not in html


def test_amber_note_and_next_not_blocked(client, setup):
    event, flight = setup
    assert "Add at least 2 teams to Intermediate Men&#x27;s before generating." in \
        client.get(f"/events/{event.pk}/setup/teams/").content.decode()
    response = client.post(f"/events/{event.pk}/setup/teams/", {"nav": "next"})
    assert response.url == f"/events/{event.pk}/setup/games/"
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_teams.py -v` FAIL.

- [ ] **Step 3: Implement** as specified. Without JS, "+ Add team" is a link to `?flight=<pk>&add=1`, which renders the same `_team_row.html` inline in the page. With JS, `hx-get` to `event_team_row` swaps it in.

- [ ] **Step 4: Run the tests** → PASS, then the full suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add league templates tests/test_setup_teams.py
git commit -m "feat(league): Teams step with inline team rows and org player type-ahead"
```

---

### Task 7: Games plan step, live summary, and Generate

**Files:**
- Modify: `league/setup_forms.py`, `league/setup_views.py`, `league/urls.py`
- Create: `templates/league/setup/games.html`, `_games_cards.html`
- Test: `tests/test_setup_games.py`

**Interfaces:**
- Consumes: `plan_views`, `FlightPlanView` (Task 3); `refresh_grids`, `editing`, `active_teams` (Task 2); `generate_event` (Task 1); `optional_reverse`.
- Produces:
  - `GamesForm(event, data=None)`: one sub-form per flight, prefix `f<pk>`. Each has `plan` (radio: once / twice / custom; initial is the resolved plan) and `w1…w<weeks>` IntegerFields (0–20, required only when the plan is custom). `overrides() -> dict[int, tuple[str, list[int]]]` works only on a valid form.
  - `games` step POST, inside `editing(event)`:
    - Saves each flight's `games_plan` and grid: the custom grid as typed, or once/twice through `refresh_grids`.
    - Sets `setup_step = 5`, calls `mark_stale` if anything changed, then re-renders the step. The no-JS "Update summary" button is `name="nav" value="stay"`, and Back is `nav=back`.
    - An invalid form re-renders with field errors and saves nothing.
  - `events/<pk>/setup/games/preview/` → `event_games_preview` (POST). It validates the same form, calls `plan_views(event, form.overrides())`, and returns `_games_cards.html` with no DB writes. An invalid form returns the cards with field errors (status 200). The `<form>` carries `hx-post` to this URL, `hx-trigger="change"`, and `hx-target="#games-cards"`.
  - `events/<pk>/setup/games/generate/` → `event_generate` (POST only; GET → 405). It saves the games form exactly as the step POST does, then:
    - If matches exist and `confirm` isn't `1` → re-renders step 5 with the panel "Regenerating replaces the current draft schedule." and a "Regenerate" button (`confirm=1`). Nothing changes.
    - Any card blocker → re-renders step 5 with the first blocker as an error message. Nothing is generated.
    - Otherwise `generate_event(event)`. On `ScheduleError` → re-renders with its text. On success → `messages.success` "Schedule drafted · {n} games over {w} weeks", then redirects to `optional_reverse("event_preview", pk) or reverse("event_list")`.
  - Cards (`_games_cards.html`):
    - Flight name and team count.
    - The plan radios, under the label "Each team plays every other team:".
    - The week grid, Wk1…WkN with a Total column. It's read-only text for once/twice and inputs for custom.
    - `empty_weeks` cells in amber with "No games this week".
    - The summary, the notes, and the blocker (in red, instead of the grid).
    - The dry-run error, if any, sits above all cards.
  - The footer button reads "Generate schedule", or "Regenerate schedule" when matches exist. It's hidden when locked, and the stale banner comes from the frame (Task 4).

- [ ] **Step 1: Write the failing tests** in `tests/test_setup_games.py`

```python
import pytest

from league.models import Flight, Match
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event, score

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(client):
    event = make_event(weeks=4, courts=2)
    flight = add_flight(event, games=(1, 1, 1, 1))
    for n in "ABCD":
        add_team(flight, n)
    client.force_login(admin_of(event.organization))
    return event, flight


def grid(flight, plan="custom", weeks=("1", "1", "1", "1")):
    data = {f"f{flight.pk}-plan": plan}
    data.update({f"f{flight.pk}-w{i}": v for i, v in enumerate(weeks, start=1)})
    return data


def test_page_shows_summary(client, setup):
    event, flight = setup
    html = client.get(f"/events/{event.pk}/setup/games/").content.decode()
    assert "Each team plays every other team:" in html
    assert "8 games · 4 per team · every pair meets 1–2 times" in html
    assert "Generate schedule" in html


def test_save_custom(client, setup):
    event, flight = setup
    client.post(f"/events/{event.pk}/setup/games/", {**grid(flight, weeks=("2", "2", "1", "1")), "nav": "stay"})
    flight.refresh_from_db(); event.refresh_from_db()
    assert flight.games_per_team_by_week == [2, 2, 1, 1] and flight.games_plan == "custom" and event.setup_step == 5


def test_preview_does_not_save(client, setup):
    event, flight = setup
    html = client.post(f"/events/{event.pk}/setup/games/preview/", grid(flight, plan="twice"),
                       HTTP_HX_REQUEST="true").content.decode()
    assert "12 games · 6 per team · every pair meets twice" in html and "<html" not in html
    flight.refresh_from_db()
    assert flight.games_plan == "custom"


@pytest.mark.parametrize("bad", ["", "-1", "x", "21"])
def test_bad_numbers(client, setup, bad):
    event, flight = setup
    for path in ("", "preview/"):
        response = client.post(f"/events/{event.pk}/setup/games/{path}",
                               {**grid(flight, weeks=(bad, "1", "1", "1")), "nav": "stay"})
        assert response.status_code == 200 and "text-danger" in response.content.decode()
    flight.refresh_from_db()
    assert flight.games_per_team_by_week == [1, 1, 1, 1]


def test_generate_goes_to_my_events_with_toast(client, setup):
    event, flight = setup
    response = client.post(f"/events/{event.pk}/setup/games/generate/", grid(flight), follow=True)
    assert response.redirect_chain[-1][0] == "/events/"
    assert "Schedule drafted · 8 games over 4 weeks" in response.content.decode()
    assert Match.objects.filter(flight=flight).count() == 8


@pytest.mark.urls("tests.future_urls")
def test_generate_goes_to_preview_when_it_exists(client, setup):
    event, flight = setup
    assert client.post(f"/events/{event.pk}/setup/games/generate/", grid(flight)).url == f"/events/{event.pk}/preview/"


def test_generate_blocked_by_preset(client, setup):
    event, flight = setup
    html = client.post(f"/events/{event.pk}/setup/games/generate/", grid(flight, plan="once")).content.decode()
    assert "Week 4 has no games — reduce weeks or choose twice." in html
    assert not Match.objects.exists()


def test_regenerate_needs_confirm_and_clears_stale(client, setup):
    event, flight = setup
    generate_event(event)
    Flight.objects.filter(pk=flight.pk).update(games_per_team_by_week=[1, 1, 1, 1])
    event.schedule_stale = True; event.save()
    url = f"/events/{event.pk}/setup/games/generate/"
    html = client.get(f"/events/{event.pk}/setup/games/").content.decode()
    assert "You changed the setup since the schedule was made. Regenerate to apply it." in html
    assert "Regenerate schedule" in html
    assert "Regenerating replaces the current draft schedule." in client.post(url, grid(flight)).content.decode()
    client.post(url, {**grid(flight, weeks=("2", "2", "1", "1")), "confirm": "1"})
    event.refresh_from_db()
    assert not event.schedule_stale and Match.objects.filter(flight=flight).count() == 12


def test_locked_hides_generate(client, setup):
    event, flight = setup
    generate_event(event); score(Match.objects.first())
    html = client.get(f"/events/{event.pk}/setup/games/").content.decode()
    assert "Generate schedule" not in html and "Regenerate schedule" not in html
    response = client.post(f"/events/{event.pk}/setup/games/generate/", {**grid(flight), "confirm": "1"}, follow=True)
    assert "Scores have been entered, so the setup is locked." in response.content.decode()
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_setup_games.py -v` FAIL.

- [ ] **Step 3: Implement** as specified.

- [ ] **Step 4: Run the tests** → PASS, then the full suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add league templates tests/test_setup_games.py
git commit -m "feat(league): Games plan step with live summary and Generate"
```

---

### Task 8: End-to-end walk-through, screen check, README

**Files:**
- Modify: `README.md`
- Test: `tests/test_setup_flow.py`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the end-to-end test** in `tests/test_setup_flow.py`. With the Django test client, as a fresh admin in a new org, walk through:
  1. `/events/new/`: "Demo League", 2027-03-02, 4 weeks, 2 courts.
  2. Scoring: defaults.
  3. Flights: `intermediate:mens` and `intermediate:mixed`.
  4. Teams: four teams per flight, all with new players.
  5. Games: post with each flight's default plan unchanged (`twice`).
  6. Generate.

  Assert:
  - the final redirect is `/events/`;
  - the toast reads "Schedule drafted · 24 games over 4 weeks";
  - `Match` count is 24;
  - `step_done(event)` is all true;
  - My Events links the row to `/events/<pk>/setup/`.

- [ ] **Step 2: Run it** → `.venv/Scripts/python -m pytest tests/test_setup_flow.py -v` PASS (fix whatever it shows is broken), then the full suite PASSES.

- [ ] **Step 3: Screen check at 390px and 1280px.** Run `manage.py tailwind build`, `migrate`, `seed_demo --reset`, then `runserver`. Log in as `admin@example.com` / `pickleball` and walk the same flow in a browser tool. Capture every step, including:
  - the flight-remove confirm;
  - the HTMX type-ahead with "Sam" typed;
  - step 5 with a long-night note and a blocker;
  - the regenerate confirm;
  - the locked banner on the seeded league after scoring one match through `/admin/`.

  On each screen, check:
  - `document.documentElement.scrollWidth <= window.innerWidth`;
  - the stepper collapses to "Step n of 5" at 390;
  - the step 5 summary updates on change without a page reload.

  Save the screenshots in the session scratchpad. Fix anything that's off and re-run the suite.

- [ ] **Step 4: README.** Add a "Create a league" section: the wizard URL, that each step saves a draft, that Generate saves a draft schedule (the preview page arrives in the next slice), and that setup locks once any score is entered.

- [ ] **Step 5: Commit**

```bash
git add tests/test_setup_flow.py README.md
git commit -m "test(league): end-to-end setup wizard walk-through; README for creating a league"
```
