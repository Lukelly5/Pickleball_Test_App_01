# Slice 4: Event page — Schedule tab, Tonight and share link (P5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give a published event its own page with these parts:
- `/events/<id>/schedule/`: one week at a time, with week pills, Division and Flight dropdowns, and a Tonight view.
- Event tabs: Schedule · Standings · Teams · Settings. Standings and Teams are stubs for now.
- Settings: the share link, with Copy and Reset.
- Public pages at `/s/<token>/…`.
- `/tonight/` in the admin nav.

**Architecture:** Four layers, each building on the last:
- **Page data** (`league/schedule_page.py`, new): a plain-data, read-only builder. It has no HTTP code and takes `today` as an argument. It turns the query string into a `ScheduleState` and one week (or tonight) into `Round`s of `Card`s.
- **Shared filters** (`league/filters.py`, new): the Division/Flight reading and dropdown lists, moved out of `league/preview.py` so the Preview and the event page use one copy.
- **Views** (`league/event_views.py`, new): one renderer serves admins, players and share-link visitors. The only difference is a `share_token` argument.
- **Templates** (`templates/league/event/`): the same templates in `base_app.html` (logged in) or `base_public.html` (share link).

State lives in the query string (`week`, `division`, `flight`, `view=tonight`). Pills, dropdowns and the Tonight button are links and GET forms with `hx-get` + `hx-push-url` that swap `#event-body`. They work as full-page loads without JS.

**Tech Stack:** Python 3.13, Django 6.1, HTMX 2.0.11 (vendored), Basecoat 1.1.0 + Tailwind via django-tailwind-cli 4.8.3, pytest 9 + pytest-django 4.14.

**Spec:** `docs/superpowers/specs/2026-11-24-event-schedule-tonight-design.md`. Also used: PRD §3 and §5 P5, and the front-end spec `docs/superpowers/specs/2026-11-19-front-end-design-system-design.md` (§5.2 nav and share-link chrome; §6.5 match card, underline tabs and segmented tabs).

## Global Constraints

**Running and testing**
- Run Python through the venv: `.venv/Scripts/python`. Tests: `.venv/Scripts/python -m pytest` from the repo root.
- The whole suite must pass after every task.
- After template changes, run `.venv/Scripts/python manage.py tailwind build`.

**Template rules (slice 1)**
- No raw hex colors in templates.
- Tailwind classes go only in templates or `frontend/stryde.css`.
- Coral and Teal fills carry `text-ink`.
- `<title>` is `<page> · Stryde`.
- Components are `{% include "components/x.html" with … only %}`.
- Toasts go through `django.contrib.messages`.
- Status badge: `components/status_badge.html` with `value`/`label`.

**Division colors** (the bar on each team row): Intermediate = `bg-brand`, Advanced = `bg-progress`, Beginner = `bg-action`. Copy the `{% if %}` from `templates/league/preview/_tile.html`.

**Today:** use `django.utils.timezone.localdate()` (`TIME_ZONE = 'America/Chicago'` is already set). Only views call it. The builder takes `today: date`.

**Access (spec §8)**
- Logged-in event pages are `@login_required`.
- Fetch the event with `get_object_or_404(Event, pk=pk, organization_id=request.user.organization_id)`, so a user with no organization gets a 404.
- On a draft event, every event-page URL (schedule, standings, teams, settings) redirects an admin to `event_preview` and gives anyone else a 404.
- Share pages fetch `Event` by `share_token` with `status__in=[PUBLISHED, COMPLETED]`; anything else is a 404.
- Settings and Reset are `@admin_required` and same organization.

**Share pages:** no app nav, no Settings tab, no "You" chip, no admin controls. Every response (partials included) sends `X-Robots-Tag: noindex`.

**HTMX:** return the partial only when `HX-Request` is set and `HX-History-Restore-Request` is not. Add `patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])`. This is the same as `league/preview_views.render_preview`.

**JS:** no new libraries and no JS file. The only exception is the few inline lines for Copy on Settings (Task 6).

**Confirms:** use the existing inline pattern (as in `templates/league/preview/page.html`). A POST without `confirm=1` re-renders the page with an amber `role="alert"` box that holds a confirm button posting `confirm=1`, plus a cancel link. Never use `confirm()`.

**Locking:** writes to `Event` take `Event.objects.select_for_update()` inside `transaction.atomic()`, as `schedule_edits.publish` already does.

**Copy, verbatim**
- "Tonight" (button)
- "Tonight — Week {n} · all flights"
- "No games tonight."
- "Next game night: {Tue Dec 9} · Week {n}"
- "No games for this flight this week." (filtered). "No games this week." (unfiltered; the spec only gives the filtered string, so this one is my call)
- "No games this week (cancelled)."
- "The schedule hasn't been published yet."
- Pill labels: "Wk{n}", or "Wk{n} · Cancelled"
- "Sitting out: {A}, {B}"
- "You", "Withdrawn", "Forfeit", "Cancelled", "Void"
- "Coming soon" (Standings and Teams stubs)
- Settings: "Share link", "Anyone with this link can see the schedule, standings and teams. No login needed.", "Copy", "Reset link", "The old link will stop working. Reset?", "Keep this link", "New share link created.", "Edit league", "Edit setup"
- Dates are written as "Tue Dec 2", using `league.display.short_day`.

## Review Focus

1. **Game night, with a filter in the link.** My Games links to `?flight=<id>` with no `week`. On a game night the visitor should see tonight's week filtered to that flight, not Tonight mode, which drops the filter. Pinned in Task 2 (`test_filter_without_week_on_game_night_stays_filtered`).
2. **A week dated today that is cancelled.** This doesn't count as a game night: there's no auto-Tonight, Tonight says "No games tonight." and points to the next non-cancelled night. Pinned in Task 2 (`test_cancelled_today_is_not_tonight`).
3. **Withdrawn teams in sit-outs.** A withdrawn team is not "sitting out". Its old matches still show, with the "Withdrawn" badge. Pinned in Task 3 (`test_sit_outs_skip_withdrawn`).
4. **One player on two flights.** The seed's shared player is on Men's and Mixed. The "You" chip should mark both teams' cards, and should appear for an admin who also plays. Pinned in Task 3 (`test_mine_marks_every_team`) and Task 4 (`test_you_chip_for_player_on_two_flights`).
5. **A logged-in user on a share link.** A user from another organization opening a share link gets the public page: no app nav and no "You" chip, even though they're logged in. A user with no organization gets a 404 on `/events/<id>/schedule/`. Pinned in Task 5 (`test_share_link_logged_in_other_org`) and Task 4 (`test_user_without_org_404`).

---

### Task 1: Share token on publish and seed

**Files:**
- Modify: `league/models.py` (on `Event`)
- Modify: `league/schedule_edits.py` (`publish`)
- Modify: `league/management/commands/seed_demo.py` (`_seed`)
- Test: `tests/test_share_token.py` (new), `tests/test_seed.py`

**Interfaces:**
- Produces:
  - `Event.ensure_share_token(self) -> str`: returns the token, and creates and saves one with `new_token()` if it's missing (`save(update_fields=["share_token"])`).
  - `Event.reset_share_token(self) -> str`: always saves a new `new_token()` and returns it.
  - `publish(event)` sets the token in the same transaction as the status flip, as `Event.objects.filter(pk=…).update(status=PUBLISHED, share_token=new_token())`, but only when the token is missing. It then mirrors both fields onto `event`.

- [ ] **Step 1: Write failing tests** in `tests/test_share_token.py`

```python
def test_ensure_creates_once(): e = make_event(); t = e.ensure_share_token(); assert t and len(t) >= 40
    e.refresh_from_db(); assert e.share_token == t and e.ensure_share_token() == t
def test_reset_changes_token(): e = make_event(); old = e.ensure_share_token(); new = e.reset_share_token()
    e.refresh_from_db(); assert new != old and e.share_token == new
def test_publish_sets_token():  # league with 4 teams, generate_event, publish(event)
    event.refresh_from_db(); assert event.status == "published" and event.share_token
def test_publish_keeps_existing_token(): event.share_token = "keep"; event.save(); publish(event)
    event.refresh_from_db(); assert event.share_token == "keep"
def test_refused_publish_sets_no_token():  # schedule_stale=True → EditRefused; token stays None
```

In `tests/test_seed.py` add `test_seed_league_has_share_token`: the published league has a token, and the draft tournament has `share_token is None`.

- [ ] **Step 2: Run them and check they fail.** `.venv/Scripts/python -m pytest tests/test_share_token.py tests/test_seed.py -v`. Expected: FAIL (`AttributeError: ensure_share_token`, and the token is None).

- [ ] **Step 3: Implement** the two `Event` methods and the `publish` change. In `seed_demo._seed`, call `league.ensure_share_token()` after the status save.

- [ ] **Step 4: Run the full suite** (`.venv/Scripts/python -m pytest`). Expected: all PASS.

- [ ] **Step 5: Commit** `feat(league): share token created on publish and in the seed`

---

### Task 2: Shared filters and schedule state (default week, Tonight)

**Files:**
- Create: `league/filters.py`
- Create: `league/schedule_page.py` (the state part; Task 3 adds the rest)
- Modify: `league/preview.py` (`parse_state` and `build_board` use `league.filters`; behavior unchanged)
- Modify: `league/display.py` (add `short_day`)
- Test: `tests/test_schedule_state.py` (new). The existing `tests/test_preview_*.py` must still pass.

**Interfaces:**
- Produces, in `league/filters.py`:
  - `read_filters(event, params: QueryDict) -> tuple[str, int | None]`: `(division_level_or_"", flight_pk_or_None)`. The rules are exactly those in today's `parse_state`: an unknown level gives `""`, and a flight that isn't in the event or isn't in the chosen division gives `None`.
  - `filter_options(event, division: str) -> tuple[list[tuple[str, str]], list[tuple[int, str]]]`: `(divisions as (level, label) by pk, flights as (pk, name) by division pk then pk, narrowed to division)`. This is the same as the lists `build_board` builds now.
- Produces, in `league/display.py`: `short_day(d: date) -> str`, e.g. `"Tue Dec 2"` (`f"{d:%a} {d:%b} {d.day}"`).
- Produces, in `league/schedule_page.py`:
  - `@dataclass(frozen=True) ScheduleState(week: int | None, division: str, flight: int | None, tonight: bool)`. `week` is `None` only when the event has no weeks, or in Tonight mode with no game today.
  - `@dataclass(frozen=True) WeekPill(number: int, label: str, cancelled: bool)`
  - `tonight_week(weeks: list[Week], today: date) -> Week | None`: the week dated `today` and not cancelled.
  - `next_game_night(weeks: list[Week], today: date) -> Week | None`: the first week, by date, dated after `today` and not cancelled.
  - `default_week(weeks: list[Week], today: date) -> int | None`, as below.
  - `read_state(event, params: QueryDict, today: date) -> ScheduleState`
  - `week_pills(weeks: list[Week]) -> list[WeekPill]`

`default_week(weeks, today) -> int | None` follows spec §4 in order:
1. a week dated today that isn't cancelled;
2. else the first week (by date) dated after today;
3. else, if any week has a date, the last week by number;
4. else Week 1 (the lowest number).

It returns `None` when there are no weeks.

`read_state` rules:
- `view=tonight` → `ScheduleState(w.number if w else None, "", None, True)`, where `w = tonight_week(weeks, today)`. The week, division and flight params are ignored.
- A valid `week` param → that week, plus `read_filters`, with `tonight=False`.
- A missing or junk `week`, with no valid division or flight and with `tonight_week` set → that week with `tonight=True` (an automatic game night).
- Anything else → `default_week`, plus `read_filters`, with `tonight=False`.

- [ ] **Step 1: Write failing tests** in `tests/test_schedule_state.py`. Use `make_event(weeks=4)`, whose weeks fall on Mar 2, 9, 16 and 23 of 2027, plus one flight. Build params with `QueryDict("…")`. MAR = `date(2027, 3, …)`.

```python
def test_short_day(): assert short_day(date(2026, 12, 2)) == "Tue Dec 2"
def test_default_today():   assert default_week(weeks, MAR(9)) == 2
def test_default_next():    assert default_week(weeks, MAR(10)) == 3
def test_default_before_season(): assert default_week(weeks, date(2027, 1, 1)) == 1
def test_default_after_season(): assert default_week(weeks, date(2027, 6, 1)) == 4
def test_default_no_dates():  # Week.objects.update(date=None) → 1
def test_default_no_weeks():  assert default_week([], MAR(9)) is None
def test_game_night_opens_tonight(): s = read_state(e, QueryDict(""), MAR(9)); assert s == ScheduleState(2, "", None, True)
def test_junk_week_on_game_night_opens_tonight(): read_state(e, QueryDict("week=abc"), MAR(9)).tonight is True
def test_week_param_wins(): assert read_state(e, QueryDict("week=3"), MAR(9)) == ScheduleState(3, "", None, False)
def test_view_tonight_clears_filters(): s = read_state(e, QueryDict(f"view=tonight&week=4&flight={f.pk}"), MAR(9)); assert s == ScheduleState(2, "", None, True)
def test_view_tonight_no_game(): assert read_state(e, QueryDict("view=tonight"), MAR(10)) == ScheduleState(None, "", None, True)
def test_filter_without_week_on_game_night_stays_filtered():  # Review Focus 1
    assert read_state(e, QueryDict(f"flight={f.pk}"), MAR(9)) == ScheduleState(2, "", f.pk, False)
def test_cancelled_today_is_not_tonight():  # Review Focus 2: week 2 cancelled
    s = read_state(e, QueryDict(""), MAR(9)); assert s.tonight is False and s.week == 3
    assert next_game_night(weeks, MAR(9)).number == 3 and tonight_week(weeks, MAR(9)) is None
def test_junk_filters_fall_back(): read_state(e, QueryDict("week=2&division=pro&flight=999"), MAR(9)) == ScheduleState(2, "", None, False)
def test_flight_outside_division_dropped():  # second flight in "advanced"; division=intermediate&flight=<adv pk> → flight None
def test_pills(): # week 3 cancelled → labels ["Wk1", "Wk2", "Wk3 · Cancelled", "Wk4"], cancelled flags match
```

- [ ] **Step 2: Run them and check they fail** (ImportError).

- [ ] **Step 3: Implement** `league/filters.py`, `short_day` and the state half of `league/schedule_page.py`. Then point `preview.parse_state` (for division and flight) and `preview.build_board` (for the `divisions` and `flights` lists) at `league.filters`.

- [ ] **Step 4: Run the full suite.** Expected: all PASS, including the untouched Preview tests.

- [ ] **Step 5: Commit** `feat(league): schedule page state: default week, Tonight, shared filters`

---

### Task 3: Rounds and match cards

**Files:**
- Modify: `league/schedule_page.py`
- Test: `tests/test_schedule_page.py` (new)

**Interfaces:**
- Consumes: `ScheduleState`, `WeekPill`, `week_pills`, `next_game_night`, `filter_options`, `short_day` (Task 2).
- Produces:

```python
@dataclass(frozen=True)
class Chip: points: int; won: bool
@dataclass(frozen=True)
class Side: team_id: int; name: str; level: str; withdrawn: bool; mine: bool; winner: bool; chips: tuple[Chip, ...]
@dataclass(frozen=True)
class Card:
    match_id: int; round_no: int; court_no: int; flight_name: str; level: str
    sides: tuple[Side, Side]; status: str  # Match.Status value
    forfeit: bool; winner_name: str        # "" when no winner
    @property
    def faded(self) -> bool: ...           # status is cancelled or void
@dataclass(frozen=True)
class Round: number: int; cards: list[Card]; sitting_out: list[str]
@dataclass(frozen=True)
class SchedulePage:
    event: Event; state: ScheduleState; pills: list[WeekPill]
    week_date: date | None; cancelled: bool
    divisions: list[tuple[str, str]]; flights: list[tuple[int, str]]
    rounds: list[Round]; has_matches: bool
    heading: str                # "Tonight — Week 2 · all flights" in Tonight mode with a game, else ""
    next_night: Week | None     # only in Tonight mode with no game today
    empty_message: str          # "" when rounds exist; else one of the verbatim empty strings
def build_page(event: Event, state: ScheduleState, today: date, my_team_ids: frozenset[int] = frozenset()) -> SchedulePage
```

Rules (spec §4–5):
- **Matches** are the event's matches in `state.week`, narrowed to `state.flight`, or else to `state.division`'s flights. Order them by `round_no`, then `court_no`. Fetch with `select_related("flight__division", "team_a", "team_b", "winner")` and `prefetch_related("games")`, so the number of queries doesn't grow with the number of matches.
- **Chips:** for side a, one chip per `GameScore`: `Chip(points_a, points_a > points_b)`, mirrored for side b.
- **Forfeit:** when `forfeited_by` is set, `forfeit=True` and the sides have no chips.
- **Winner:** `Side.winner` is `team_id == match.winner_id`, and `winner_name` is the winner's name.
- **Mine:** `Side.mine` is `team_id in my_team_ids`.
- **Sit-outs:** only when `state.flight` is set. For each round, list the flight's teams that aren't withdrawn and that aren't in any non-cancelled, non-void match of that round, sorted by name. Otherwise use `[]`.
- **Cancelled week:** the pill for the week is cancelled. It gets no rounds and `empty_message="No games this week (cancelled)."`.
- **Empty messages:**
  - `has_matches` is False (the event has no matches anywhere): "The schedule hasn't been published yet."
  - Tonight mode with no game: "No games tonight."
  - No rounds while a filter is set: "No games for this flight this week."
  - No rounds otherwise: "No games this week."

- [ ] **Step 1: Write failing tests** in `tests/test_schedule_page.py`. The fixture is one intermediate men's flight with 5 teams and `games=(2, 2, 2, 2)`, plus one advanced mixed flight with 4 teams, then `generate_event`. Call `build_page(e, ScheduleState(…), MAR(9))`.

```python
def test_rounds_and_courts_in_order(): keys = [(c.round_no, c.court_no) for r in p.rounds for c in r.cards]; assert keys == sorted(keys)
    assert [r.number for r in p.rounds] == sorted({k[0] for k in keys})
def test_flight_filter(): every card.flight_name == men.name
def test_division_filter(): every card.level == "advanced"
def test_sit_outs_one_flight_only(): # flight=men → each round's sitting_out == sorted(names of men teams not in that round); no filter → all []
def test_sit_outs_skip_withdrawn():  # Review Focus 3: withdraw one men team (withdrawn_at=now)
    assert withdrawn.name not in any r.sitting_out; its existing card side has withdrawn=True
def test_scored_card(): m = first men match; score(m, 11, 9, 1); score(m, 9, 11, 2); score(m, 11, 5, 3); m.status="final"; m.winner=m.team_a; m.save()
    card → sides[0].chips == (Chip(11, True), Chip(9, False), Chip(11, True)); sides[0].winner and not sides[1].winner; card.winner_name == m.team_a.name
def test_forfeit_card(): m.forfeited_by=m.team_b; m.winner=m.team_a; m.status="final" → card.forfeit, chips == () on both sides, winner_name == team_a.name
def test_cancelled_and_void_matches_faded(): one match status "cancelled", one "void" → both cards faded with status kept
def test_cancelled_week(): week 2 cancelled; state week 2 → rounds == [], empty_message == "No games this week (cancelled)."
def test_mine_marks_every_team():  # Review Focus 4: my_team_ids = {men team, mixed team}
    every side whose team_id in ids has mine=True; others False
def test_tonight_with_game(): ScheduleState(2, "", None, True) → heading == "Tonight — Week 2 · all flights", both flights' cards present, all sitting_out == []
def test_tonight_no_game(): ScheduleState(None, "", None, True), today MAR(10) → rounds == [], empty_message == "No games tonight.", next_night.number == 3
def test_tonight_no_later_night(): today date(2027, 6, 1) → next_night is None
def test_no_matches_at_all(): Match.objects.all().delete() → has_matches False, empty_message == "The schedule hasn't been published yet."
def test_filtered_empty_week(): men games plan for week 4 set to 0, regenerate → flight=men week=4 → "No games for this flight this week."
def test_query_count_flat(django_assert_max_num_queries): with django_assert_max_num_queries(12): build_page(...)
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement `build_page`** and the dataclasses.
- [ ] **Step 4: Run the full suite.** Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): read-only schedule builder: rounds, match cards, sit-outs`

---

### Task 4: Event page, Schedule tab, and stub tabs (logged in)

**Files:**
- Create: `league/event_views.py`
- Modify: `league/urls.py`
- Modify: `templates/base_app.html`: wrap the title row `<div class="mb-5 …">…</div>` in `{% block page_header %}…{% endblock %}` (no other change)
- Modify: `templates/base_public.html`: replace the `<main>` classes with `{% block main_class %}mx-auto w-full max-w-md px-4 pb-16{% endblock %}`
- Create templates under `templates/league/event/`:
  - `page.html`: `{% extends base_template %}`; overrides `page_header` to empty and `main_class` to `mx-auto w-full max-w-[1200px] px-4 pb-16`; `content` = `_header.html` + `<div id="event-body">{% include "league/event/_schedule_body.html" %}</div>`
  - `_header.html`: the event name, the status badge (Published/Completed), the Tonight button, and the underline tabs
  - `_schedule_body.html`: the dropdown GET form, the pills with the week date, the heading, rounds of `_card.html`, sit-outs, the empty message, and the next-game-night link
  - `_card.html`: the match card
  - `coming_soon.html`: the Standings/Teams stub
- Modify: `tests/test_preview_publish.py::test_publish_confirmed` (Location becomes `f"/events/{league.pk}/schedule/"`), and `tests/test_preview_flow.py` (the My Events row now links to `/schedule/`)
- Test: `tests/test_event_schedule.py` (new)

**Interfaces:**
- Consumes: `read_state`, `build_page`, `SchedulePage` (Tasks 2–3); `accounts.roles.player_for`; `ui.nav.NavLink`.
- Produces, in `league/event_views.py` (Tasks 5–7 use these):
  - `event_tabs(event, active: str, *, token: str | None = None, admin: bool = False) -> list[NavLink]`. The labels are Schedule, Standings and Teams, plus Settings when `admin and token is None`. The URLs are the `event_*` names, or the `share_*` names when `token` is given. Use `icon=""`.
  - `member_event(request, pk: int) -> Event`: 404 unless the event is in the user's organization.
  - `draft_guard(request, event) -> HttpResponse | None`: when the event isn't visible, a redirect to `event_preview` for admins and `Http404` for anyone else.
  - `render_schedule(request, event, *, token: str | None = None) -> HttpResponse`. It builds the context `{event, page, tabs, base_template, schedule_url, share: bool, is_admin}`. `schedule_url` is the tab's own URL, which pills and forms point at. `my_team_ids` comes from `player_for(user)`'s teams in this event, and is empty when `token` is given.
  - `render_coming_soon(request, event, active: str, *, token=None) -> HttpResponse`
- URLs (names are exact):
  - `events/<int:pk>/schedule/` `event_schedule`
  - `events/<int:pk>/standings/` `event_standings`
  - `events/<int:pk>/teams/` `event_teams`

**Markup decisions:**
- Pills are `<a href="{{ schedule_url }}?week=N&{{ filter_query }}" hx-get=… hx-target="#event-body" hx-push-url="true">`. The selected pill has `aria-current="page"` and `bg-brand text-white`. Pills sit in an `overflow-x-auto` row with `whitespace-nowrap`.
- The form is `method="get"` with a hidden `week` input. It carries `hx-get`, `hx-target="#event-body"`, `hx-push-url="true"` and `hx-trigger="change"`, plus an Apply button for no-JS use.
- The Tonight button is `href="{{ schedule_url }}?view=tonight"`, with the same hx attributes.
- Cards have `data-card="{{ card.match_id }}"`, and faded ones add `data-faded` and `opacity-50`. The meta line reads "Round {r} · Court {c} · {flight}" in small uppercase with letter-spacing. The winner's row is `font-bold`. A won chip uses `bg-progress text-ink`. A "You" chip has `data-you`.
- The underline tabs are `<nav aria-label="Event">`, and the active one has `aria-current="page"`.

- [ ] **Step 1: Write failing tests** in `tests/test_event_schedule.py`. The fixture is a published league with 4 teams and `generate_event`, with week dates set so Week 2 = `timezone.localdate()` and the others 7 days apart. `player` is a `User` linked to a `Player` on team "Dinkers".

```python
def test_admin_sees_all_tabs(client):  html has Schedule, Standings, Teams, Settings tab links; 'aria-current="page"' on Schedule
def test_game_night_opens_tonight(client): "Tonight — Week 2 · all flights" in html
def test_week_pill_and_date(client): get ?week=3 → 'Wk3' pill aria-current, short_day(week3.date) in html
def test_player_sees_no_settings(client): login player → 200, no "/settings/" link, data-you present on Dinkers' cards
def test_you_chip_for_player_on_two_flights(client):  # Review Focus 4: player on a men's and a mixed team → data-you on cards of both flights
def test_other_org_404(client); def test_user_without_org_404(client)  # Review Focus 5
def test_anonymous_redirects_to_login(client): r.status_code == 302 and "/login/" in r["Location"]
def test_draft_admin_redirects_to_preview(client): status draft → Location == f"/events/{pk}/preview/"
def test_draft_player_404(client)
def test_htmx_partial(client): HTTP_HX_REQUEST="true" → no "<html", contains 'data-card'; Vary has HX-Request
def test_history_restore_full_page(client): HX-Request + HX-History-Restore-Request → "<html" in body
def test_stub_tabs(client): /standings/ and /teams/ → "Coming soon", active tab marked
def test_completed_event_visible(client): status completed → 200, "Completed" badge
def test_no_matches_message(client): delete matches → "The schedule hasn't been published yet."
def test_publish_lands_on_schedule(client): draft + publish confirm → Location == f"/events/{pk}/schedule/"
```

- [ ] **Step 2: Run them and check they fail** (404s and NoReverseMatch).
- [ ] **Step 3: Implement** the views, URLs, base-template blocks and templates. Update the two existing tests listed above.
- [ ] **Step 4: Run** `.venv/Scripts/python manage.py tailwind build`, then the full suite. Expected: all PASS. The `/events/` "Rows link" tests already expect `/schedule/` for published events.
- [ ] **Step 5: Commit** `feat(league): event page with Schedule tab, Tonight view and stub tabs`

---

### Task 5: Share-link pages

**Files:**
- Modify: `league/event_views.py`, `league/urls.py`
- Test: `tests/test_share_pages.py` (new)

**Interfaces:**
- Consumes: `render_schedule(…, token=)`, `render_coming_soon(…, token=)`, `event_tabs(…, token=)` (Task 4); `Event.reset_share_token` (Task 1).
- Produces:
  - `shared_event(token: str) -> Event`: 404 unless the token matches and the event is published or completed.
  - URL names `share_schedule`, `share_standings` and `share_teams`, at `s/<str:token>/schedule/`, `…/standings/` and `…/teams/`.
  - With a token, `render_schedule` uses `base_template="base_public.html"`, adds `X-Robots-Tag: noindex` to every response, shows no "You" chip and no Settings tab, and points pills and the Tonight button at `share_schedule`.

- [ ] **Step 1: Write failing tests** with the same fixture as Task 4 plus `event.ensure_share_token()`. Use an anonymous `Client()` unless the test says otherwise.

```python
def test_share_schedule_public(client): 200; 'data-nav' not in html; "/settings/" not in html; tabs link to f"/s/{t}/standings/" and f"/s/{t}/teams/"; r["X-Robots-Tag"] == "noindex"
def test_share_keeps_tonight(client): "Tonight — Week 2 · all flights" in html; Tonight button href starts f"/s/{t}/schedule/?view=tonight"
def test_share_pills_stay_on_share_url(client): f'href="/s/{t}/schedule/?week=3' in html
def test_share_htmx_partial_noindex(client): HX-Request → partial, X-Robots-Tag noindex
def test_share_stubs(client): standings and teams → 200 "Coming soon", noindex
def test_bad_token_404(client); def test_draft_with_token_404(client)  # set token, status draft → 404
def test_reset_token_old_404(client): old = token; event.reset_share_token() → old URL 404, new URL 200
def test_share_link_logged_in_other_org(client):  # Review Focus 5: login user of another org who is a Player on Dinkers by email in THAT org → 200, no data-you, 'data-nav' absent
def test_completed_share_visible(client)
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite.** Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): public share-link pages at /s/<token>/`

---

### Task 6: Settings tab, Copy and Reset

**Files:**
- Modify: `league/event_views.py`, `league/urls.py`
- Create: `templates/league/event/settings.html` (extends `league/event/page.html`'s frame, or uses `_header.html` directly; the builder decides)
- Test: `tests/test_event_settings.py` (new)

**Interfaces:**
- Consumes: `member_event`, `draft_guard`, `event_tabs` (Task 4); `ensure_share_token` and `reset_share_token` (Task 1).
- Produces:
  - `event_settings(request, pk)` (`@admin_required`), URL name `event_settings`, path `events/<int:pk>/settings/`.
  - `event_share_reset(request, pk)` (`@admin_required @require_POST`), URL name `event_share_reset`, path `events/<int:pk>/settings/share/reset/`.
  - Context: `share_url = request.build_absolute_uri(reverse("share_schedule", args=[token]))`, and `confirm` is `"reset"` or `None`.

**Page:** a readonly `<input id="share-url" value="{{ share_url }}" onfocus="this.select()">` and a Copy button. The Copy button uses an inline `onclick` that calls `navigator.clipboard.writeText(document.getElementById('share-url').value)` and sets its own label to "Copied". The Reset form posts with no `confirm`. The confirm box uses the verbatim copy plus `confirm=1`. The Edit setup link goes to `event_setup`.

- [ ] **Step 1: Write failing tests**

```python
def test_settings_shows_absolute_share_url(client): admin GET → f"http://testserver/s/{event.share_token}/schedule/" in html; "Copy" and "Reset link" present; href to f"/events/{pk}/setup/"
def test_settings_creates_missing_token(client): share_token None, published → GET → event.share_token set
def test_reset_asks_first(client): POST {} → "The old link will stop working. Reset?" in html and token unchanged
def test_reset_confirmed(client): POST confirm=1 → 302 to settings; token changed; toasts == ["New share link created."]; old /s/<old>/schedule/ 404
def test_settings_player_403(client); def test_settings_other_org_404(client)
def test_settings_draft_redirects_to_preview(client): and token stays None
def test_reset_requires_post(client): GET → 405
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `tailwind build`, then the full suite. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): event Settings tab with share link copy and reset`

---

### Task 7: The `/tonight/` app nav tab

**Files:**
- Modify: `league/event_views.py`, `league/urls.py`
- Create: `templates/league/tonight.html` (extends `base_app.html`, title "Tonight")
- Modify: `tests/test_nav.py`, only if an assertion lists the real admin tabs without `future_urls` (check; `test_unbuilt_pages_are_hidden` uses `nav_urls_partial` and is unaffected)
- Test: `tests/test_tonight.py` (new)

**Interfaces:**
- Consumes: `tonight_week`, `next_game_night` (Task 2); `short_day`.
- Produces: `tonight(request)` (`@admin_required`), URL name `tonight`, path `tonight/`. It only looks at the user's organization's events with `status=PUBLISHED`, and uses `today = timezone.localdate()`.
  - Exactly one event has `tonight_week`: redirect to `reverse("event_schedule", args=[pk]) + "?view=tonight"`.
  - Several: a list of links, one per event, reading "{event name} · Week {n}", each going to its `?view=tonight` URL.
  - None: "No games tonight." Then, if any event has a `next_game_night`, the earliest one across events reads "Next game night: {event name} · {short_day} · Week {n}" and links to `?week=n`.

- [ ] **Step 1: Write failing tests**

```python
def test_one_event_redirects(client): Location == f"/events/{pk}/schedule/?view=tonight"
def test_several_events_listed(client): two published with a week today → 200, both "· Week 2" links
def test_none_shows_next(client): weeks all after today → "No games tonight." and "Next game night:" with event name
def test_none_and_no_next(client): weeks in the past → "No games tonight." and no "Next game night"
def test_drafts_completed_and_other_orgs_ignored(client): draft and completed events with week today, other org published with week today → "No games tonight."
def test_cancelled_week_today_ignored(client)
def test_player_403(client)
def test_admin_nav_shows_tonight(client): GET /events/ as admin → 'href="/tonight/"' in html
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite.** Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): Tonight tab in the admin nav`

---

### Task 8: My Games links, `seed_demo --tonight`, docs, and the walk-through

**Files:**
- Modify: `templates/league/my_games.html`. Wrap each card's team name in a link to `{% url 'event_schedule' team.flight.division.event.pk %}?flight={{ team.flight_id }}`.
- Modify: `league/management/commands/seed_demo.py`
- Modify: `README.md`. Add a section "Event page and share link" after "Review and publish a schedule". In "Demo data", document `--tonight`, and change "The league is published" to mention the share link on Settings.
- Modify: `Pickleball League Manager — PRD, ERD & Scheduling Spec.md` §9 checklist. Tick Auth, P2, P3, P4 and P5.
- Test: `tests/test_seed.py`, `tests/test_my_events.py`, `tests/test_event_flow.py` (new)

**Interfaces:**
- `seed_demo --tonight`: re-dates the demo league's weeks. With `today = timezone.localdate()`, Week n is dated `today + 7*(n-2)` days and `start_date = today - 7 days`. The tournament is untouched.
  - With a fresh seed or `--reset`, it re-dates the newly built league.
  - When the demo already exists and `--reset` isn't given, it re-dates the existing league and prints "Demo league re-dated: Week 2 is tonight." It doesn't print "already exists".
  - Without the flag, nothing changes.

- [ ] **Step 1: Write failing tests**

```python
# test_seed.py
def test_seed_tonight_dates_week_2_today(): call_command("seed_demo", "--tonight"); dates == [today-7, today, today+7, today+14]
def test_seed_tonight_on_existing_demo(): seed; seed --tonight → same dates, still 1 demo org, league still published with same matches count
def test_seed_without_tonight_unchanged(): week 1 date == date(2027, 3, 2)
# test_my_events.py
def test_my_games_links_to_flight_schedule(client): f'href="/events/{e.pk}/schedule/?flight={team.flight_id}"' in html
# test_event_flow.py
def test_publish_to_share_walkthrough(client):
    call_command("seed_demo", "--tonight"); league = Event.objects.get(name="Spring Tuesday League")
    league.status = "draft"; league.share_token = None; league.save()
    login admin@example.com; POST preview publish confirm=1 → follow → final URL f"/events/{pk}/schedule/", "Tonight — Week 2 · all flights"
    GET ?week=3 → Wk3 current; GET ?week=3&division=advanced → only advanced cards; GET ?view=tonight → heading again
    settings → share_url; Client() anonymous GET share path → 200, no 'data-nav', no '/settings/'
    login player@example.com; /me/ → link to schedule?flight=…; follow it → 200 with data-you
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement** the template link, the seed flag, the README and the PRD ticks.
- [ ] **Step 4: Run** `tailwind build`, then the full suite. Expected: all PASS.
- [ ] **Step 5: Browser check at 390 px.**
  - Run `.venv/Scripts/python manage.py seed_demo --reset --tonight`, then `runserver`.
  - With the Playwright tools, resize to 390×844 and open the admin Schedule tab, the Tonight view, Settings and the share page (logged out).
  - On each page, `browser_evaluate` `document.documentElement.scrollWidth <= window.innerWidth` must be `true`.
  - Also take a screenshot of each page and look at it.
- [ ] **Step 6: Commit** `feat(league): My Games links, seed_demo --tonight, P5 walk-through and docs`
