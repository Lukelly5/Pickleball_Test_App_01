# Slice 3: Schedule Preview (P4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `/events/<id>/preview/`, the page where the league director reviews a generated schedule week by week. On it she can:
- swap games, swap teams, or move a game into an open court, with clash checks;
- read a fairness panel;
- regenerate the schedule or publish it.

The setup wizard also learns two things: a rename no longer marks the schedule stale, and a published league shows warnings.

**Architecture:** Four layers, each building on the last:
- **Engine** (`scheduler/swap.py`): adds `move_game`.
- **Bridge** (`league/schedule_edits.py`, new): the database edits, publish, and regenerate, each inside the Event row lock.
- **Page data** (`league/preview.py`, new): a plain-data builder for the grid, the click rules, and the fairness panel. It has no HTTP code, so it's unit-testable.
- **Views** (`league/preview_views.py`, new): thin wrappers that render `templates/league/preview/`.

All page state (week, filters, pick) lives in the query string. A click is an HTMX GET (to select) or POST (to act) that swaps in `#preview-board`. With no JS, the same links and forms do full-page loads.

**Tech Stack:** Python 3.13, Django 6.1, HTMX 2.0.11 (vendored; `base.html` already sends the CSRF header), Basecoat 1.1.0 + Tailwind via django-tailwind-cli 4.8.3, pytest 9 + pytest-django 4.14.

**Spec:** `docs/superpowers/specs/2026-11-23-schedule-preview-design.md`, with PRD §5 P4 and the front-end spec `docs/superpowers/specs/2026-11-19-front-end-design-system-design.md` (§5 match tile / fairness panel / segmented tabs, §7 P4 mockup, division colors).

## Global Constraints

**Running and testing**
- Run Python through the venv: `.venv/Scripts/python`. Tests: `.venv/Scripts/python -m pytest` from the repo root.
- The whole suite must pass after every task.
- After template changes, run `.venv/Scripts/python manage.py tailwind build`.

**Slice-1 template rules**
- No raw hex colors in templates.
- Tailwind classes go only in templates or `frontend/stryde.css`.
- Coral and Teal fills carry `text-ink`.
- `<title>` is `<page> · Stryde`.
- Components are `{% include "components/x.html" with … only %}`.
- Toasts go through `django.contrib.messages`.
- Status badge: `components/status_badge.html` with `value`/`label`.

**Division colors** (bar on each team in a tile): Intermediate = `bg-brand` (Cobalt), Advanced = `bg-progress` (Teal), Beginner = `bg-action` (Coral).

**Access**
- Every preview view is `@admin_required`.
- The event is fetched with `get_object_or_404(Event, pk=pk, organization=request.user.organization)`, of any type.
- Another org's event is a 404 on every preview URL.

**Locking and errors**
- Every write (edit, regenerate, publish) runs inside `transaction.atomic()` with `Event.objects.select_for_update().get(pk=…)` first.
- Catch `django.db.models.RestrictedError`, never `ProtectedError`.

**No new JS:** no new JS libraries and no custom JS file. HTMX attributes only. Everything works as plain links and form posts.

**Confirms:** use the wizard's existing inline pattern, not a modal and not `confirm()`. The first POST without `confirm=1` re-renders the page with an amber `role="alert"` box that holds a confirm button posting `confirm=1`, plus a cancel link.

**Copy, verbatim:**
- "Draft · not visible to players" / "Published"
- "Inputs changed — regenerate to apply them."
- "No schedule yet" (empty state), with a link "Go to the Games step"
- "No games this week"
- "Open court"
- "Cancelled" (tile), "Week {n} · Cancelled" (tab), "Withdrawn" (team badge)
- "Can't move: games must stay in the same week."
- "Can't move: Court {c} in Round {r} already has a game."
- "Can't move: Week {w} only has Rounds 1–{max}."
- "Can't move: there {is/are} only {n} court(s)."
- Clash: "Can't {swap|move}: {who} would play on Court {a} and Court {b} in Round {r}." (`who` comes from the engine's existing `_clash`, e.g. "Team Smashers")
- "Can't change a game that already has a score."
- "Can't change a game with a withdrawn team."
- "Week {n} is cancelled, so its games can't change."
- "That game is no longer on the schedule. Refresh and try again."
- "Regenerate the schedule? This replaces every game, including your swaps and moves."
- "Players have already seen this schedule."
- "Schedule regenerated · {n} games over {w} weeks"
- "Publish {event}? Players will be able to see the schedule."
- "{event} published"
- "Regenerate first: inputs changed since this schedule was made."
- "Generate a schedule before publishing."
- Wizard banner (published): "This league is published, so players can see its schedule. Renames show up right away. Removing a team or flight removes its games from the schedule immediately. Other changes take effect when you regenerate, which replaces the schedule."
- Team delete confirm (published): "Delete {team}? This also removes {flight}'s games from the published schedule. Regenerate to rebuild them."
- Flight removal (published) adds: " Its games will also disappear from the published schedule."

**Pluralizing:** "game/games", "week/weeks", "round/rounds", "court/courts" (1 → singular).

**Corrections to the spec, decided while planning:**
- The spec says "Basecoat confirm dialog". The plan uses the wizard's inline confirm pattern instead (see **Confirms** above). It's already in the app, works without JS, and still never uses `confirm()`.
- The spec's §4 sketch shows "6:30" next to rounds. No start time exists, so the label is just "Round {n}".

## Review Focus

1. **A stale pick or target.** She regenerates in one tab, then clicks in an old tab, so `pick=g999` names a match that's gone. Selecting ignores an unknown pick. Acting returns "That game is no longer on the schedule. Refresh and try again." Never a 500. (Tasks 2, 5)
2. **Junk query values** (`week=abc`, `week=99`, `division=bogus`, `flight=x`, `pick=zzz`). Each falls back to its default (week 1, All, no pick), and the page renders with a 200. (Tasks 3, 4)
3. **A direct POST that bypasses the UI.** Editing a scored match, a withdrawn team's match, a cancelled week, a different event's match, or posting a cross-week target. Each is refused with its message and changes nothing. (Task 2)
4. **Filtered views.** With a Flight filter on, games outside it are faded and have no link or form. Open courts stay clickable, and the fairness panel shows only the filtered flights. (Tasks 3, 4)
5. **Swapping two games' slots** must not trip the `one_match_per_court_per_round` unique constraint, and must not leave a row parked on the spare court if the second write fails. The whole edit is one transaction. (Task 2)

---

### Task 1: Engine `move_game`

**Files:**
- Modify: `scheduler/swap.py` (add `move_game`; give `_check_week` a `verb` parameter)
- Modify: `scheduler/__init__.py` (export `move_game`)
- Test: `tests/test_swap.py`

**Interfaces:**
- Produces: `move_game(schedule: Schedule, slot: Slot, target: Slot) -> Schedule`, raising `SwapConflict`. `Slot = (week, round_no, court_no)`.
- Produces: `_check_week(schedule, week, verb="swap")`. Existing callers are unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/test_swap.py`. Use `t1()` (4 teams, 2 courts, weeks of 2 games each → 2 rounds in week 1).
  - `test_move_into_open_court`: build a schedule with an open slot. Generate with `courts=3` from `make_flight(4, [2,2,2,2])` and find a `(1, r, c)` with no match. Move a game from a round where its teams don't play in round `r`. Assert the moved match now has `(round_no, court_no) == (r, c)`, the match count is unchanged, and the input schedule is untouched.
  - `test_move_same_slot_is_noop`: `move_game(s, x, x) is s`.
  - `test_move_rejections` (parametrized), each asserting `str(e.value)` exactly:
    - target in week 2 → "Can't move: games must stay in the same week."
    - target occupied `(1,1,2)` → "Can't move: Court 2 in Round 1 already has a game."
    - target round = max round + 1 → "Can't move: Week 1 only has Rounds 1–2."
    - target court 3 with `courts=2` → "Can't move: there are only 2 courts."
  - `test_move_clash_message`: move a game into an open court in a round where one of its teams already plays. Assert `re.fullmatch(r"Can't move: Team T\d would play on Court \d and Court \d in Round \d\.", …)`.
  - `test_move_unknown_slot_raises_keyerror`: same as `_find` today.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_swap.py -v`. Expected: the new tests FAIL (ImportError on `move_game`).

- [ ] **Step 3: Implement.**
  - `_check_week` gains `verb: str = "swap"`, used in the message.
  - `move_game` checks in this order:
    1. `_find(slot)`;
    2. same slot → return the input;
    3. same week;
    4. court ≤ `schedule.courts`;
    5. round ≤ the highest `round_no` in that week;
    6. target empty;
    7. build the candidate with `replace(m, round_no=…, court_no=…)`;
    8. `_check_week(candidate, week, verb="move")`.
  - Export `move_game` from `scheduler/__init__.py`.

- [ ] **Step 4: Run** the full suite. Expected: PASS.

- [ ] **Step 5: Commit** `feat(scheduler): move_game into an open court with clash check`

---

### Task 2: Bridge edits, publish, regenerate (`league/schedule_edits.py`)

**Files:**
- Create: `league/schedule_edits.py`
- Test: `tests/test_schedule_edits.py`

**Interfaces:**
- Consumes: `scheduler.swap_games`, `scheduler.swap_teams`, `scheduler.move_game`, `SwapConflict`, `ScheduleError`; `league.scheduling.load_schedule`, `generate_event`; `league.setup_preview.plan_views`.
- Produces:
  ```python
  class EditRefused(Exception): ...          # str(exc) is the user-facing message

  def scored_match_ids(event: Event) -> set[int]   # FINAL, forfeited, or has any GameScore
  def swap_games(event: Event, match_a: int, match_b: int) -> None
  def swap_teams(event: Event, a: tuple[int, str], b: tuple[int, str]) -> None   # side "a" | "b"
  def move_game(event: Event, match_id: int, round_no: int, court_no: int) -> None
  def publish(event: Event) -> None
  def regenerate(event: Event) -> scheduler.Schedule   # raises scheduler.ScheduleError
  ```

- [ ] **Step 1: Write the failing tests** in `tests/test_schedule_edits.py`. Use `make_event(weeks=4, courts=3)`, `add_flight(..., games=(2,2,2,2))`, four `add_team`s, then `generate_event`.
  - **Swaps and moves:**
    - `test_swap_games_trades_slots`: the two rows' `(round_no, court_no)` trade, and every other row is unchanged.
    - `test_swap_teams_trades_teams`: both cases, two matches and one match (`(m, "a")`, `(m, "b")` flips the sides).
    - `test_move_game_writes_slot`: move a game into a free slot the engine accepts.
  - **Refusals** (parametrized): each raises `EditRefused` with the exact Global Constraints copy, and the DB is unchanged (compare a snapshot of `(id, week_id, round_no, court_no, team_a_id, team_b_id)`):
    - an engine clash (message passed through);
    - a match from another event → "That game is no longer on the schedule. Refresh and try again.";
    - an unknown id → the same message;
    - a scored match (add a `GameScore` via `tests.factories.score`) → "Can't change a game that already has a score.";
    - a withdrawn team's match (set `withdrawn_at`) → "Can't change a game with a withdrawn team.";
    - a match in a week with `status=CANCELLED` → "Week {n} is cancelled, so its games can't change.";
    - a move target holding a `CANCELLED` match row → "Can't move: Court {c} in Round {r} already has a game."
  - **Rollback:** `test_swap_games_rolls_back_on_failure`. Monkeypatch `Match.save` (or the second write) to raise after the first write. Assert no row has `court_no > event.courts`.
  - **Publish:**
    - `test_publish`: draft → `status == "published"`.
    - Stale → `EditRefused("Regenerate first: inputs changed since this schedule was made.")`.
    - No matches → `EditRefused("Generate a schedule before publishing.")`.
    - Already published → no-op.
  - **Regenerate:**
    - `test_regenerate`: replaces the matches and clears `schedule_stale`.
    - When `plan_views` has a blocker (a team with 1 player), it raises `ScheduleError` with that blocker text, and the matches are unchanged.
  - **Edits don't touch stale:** `test_edits_do_not_mark_stale`.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_schedule_edits.py -v`. Expected: FAIL (module missing).

- [ ] **Step 3: Implement** with one private helper, `_locked_matches(event, ids) -> dict[int, Match]`, that:
  1. locks the Event row;
  2. fetches the matches filtered by `flight__division__event=event` (a missing id → the "no longer on the schedule" refusal);
  3. checks scored, withdrawn (either team's `withdrawn_at`), and cancelled week.

  For each edit:
  1. Load `load_schedule(event)`.
  2. Run the engine function on `(week.number, round_no, court_no)` slots. Turn `SwapConflict` into `EditRefused(str(exc))`.
  3. Write only the changed rows.

  Specifics:
  - **`swap_games` writes:** park row A on `court_no = event.courts + 1`, save B into A's old slot, then save A into B's old slot. This is all inside the one atomic block.
  - **`move_game`** first checks `Match.objects.filter(week=…, round_no=…, court_no=…).exists()` across all statuses (this catches the cancelled/void rows the engine can't see).
  - **`regenerate`:**
    1. `views, _ = plan_views(event)`;
    2. the first `v.blocker` → `raise ScheduleError(blocker)`;
    3. `return generate_event(event)`, which takes its own lock and does its own `has_scores` check.

- [ ] **Step 4: Run** the full suite. Expected: PASS.

- [ ] **Step 5: Commit** `feat(league): schedule edits, publish and regenerate behind the event lock`

---

### Task 3: Page data: grid, clicks, fairness (`league/preview.py`)

**Files:**
- Create: `league/preview.py`
- Modify: `scheduler/fairness.py` (extract `pair_meet_text(counts: list[int]) -> str` from `summary_line`; `summary_line` calls it, and its output is unchanged)
- Test: `tests/test_preview_data.py`

**Interfaces:**
- Consumes: `scored_match_ids` (Task 2), `scheduler.fairness_report`, `pair_meet_text`, `event_flights(event, include_withdrawn=True)`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class TeamSlot:  key: str; name: str; level: str; withdrawn: bool         # key "t<match_id>a" / "t<match_id>b"

  @dataclass(frozen=True)
  class Tile:
      key: str            # "g<match_id>" | "o<round>-<court>" | "x<match_id>" (cancelled/void)
      kind: str           # "game" | "open" | "cancelled"
      round_no: int; court_no: int
      match_id: int | None
      flight_name: str; level: str          # "" for open tiles
      teams: tuple[TeamSlot, ...]           # () for open tiles
      locked: bool        # scored, withdrawn team, or cancelled week: not clickable
      faded: bool         # outside the filter: not clickable
      actions: dict[str, tuple[str, str | None]]   # click key (tile or team key) → resolve_click result; {} when not clickable

  @dataclass(frozen=True)
  class WeekTab:  number: int; label: str; cancelled: bool

  @dataclass(frozen=True)
  class Board:
      event: Event; week: int; tabs: list[WeekTab]; courts: int
      rows: list[list[Tile]]     # rows[i] is Round i+1, one Tile per court 1..courts
      read_only: bool            # the week is cancelled
      division: str; flight: int | None; pick: str | None   # cleaned state
      divisions: list[tuple[str, str]]       # (level, label) the event has
      flights: list[tuple[int, str]]         # (pk, name), narrowed to the chosen division

  @dataclass(frozen=True)
  class FairLine:  label: str; text: str; ok: bool; chip: str = ""

  @dataclass(frozen=True)
  class FlightFairness:  flight_name: str; lines: list[FairLine]

  def parse_state(event: Event, params: QueryDict) -> dict   # {"week", "division", "flight", "pick"}, junk → defaults
  def build_board(event: Event, state: dict) -> Board
  def resolve_click(board: Board, target: str) -> tuple[str, str | None]
      # → ("select", new_pick_or_None) | ("swap_games"|"swap_teams"|"move", target_key)
  def fairness(event: Event, week: int, flight_ids: set[int] | None) -> list[FlightFairness]
  ```

- [ ] **Step 1: Write the failing tests.**

  **`parse_state`.** `week` defaults to 1 and must be one of the event's week numbers. `division` must be a `Division.Level` the event has, else `""`. `flight` must be one of the event's flight pks (and inside the chosen division), else `None`. `pick` must match `^(g\d+|t\d+[ab])$` and name a match on the current week, else `None`. Test each junk value from Review Focus 2.

  **`build_board`:**
  - The rows run from 1 to the max `round_no` of any match that week, of any status. Each row has exactly `courts` tiles in court order.
  - Empty cells are `kind="open"`. Cancelled/void matches are `kind="cancelled"` and `locked`.
  - A scored match is `locked`. A withdrawn team's match is `locked`, with that `TeamSlot.withdrawn=True`.
  - A cancelled week gives `read_only=True` and tab label `"Week 3 · Cancelled"`.
  - With a flight filter, the other flights' tiles are `faded` and open tiles are not faded.
  - A week with no matches gives `rows == []`.
  - `actions` is filled for every clickable key, using `resolve_click` with the board's pick. Locked, faded and cancelled tiles get `{}`, and so does every tile in a read-only week.
  - With `division="advanced"`, `board.flights` lists only Advanced flights.

  **`resolve_click`.** A table test covering every row of spec §5's table:
  - no pick + game → `("select", "g5")`;
  - no pick + team → `("select", "t5a")`;
  - pick `g5` + `g7` → `("swap_games", "g7")`;
  - pick `g5` + `t7b` → `("swap_games", "g7")`;
  - pick `g5` + `g5` or `t5a` → `("select", None)`;
  - pick `g5` + `o2-3` → `("move", "o2-3")`;
  - pick `t5a` + `t7b` → `("swap_teams", "t7b")`;
  - pick `t5a` + `t5a` → `("select", None)`;
  - pick `t5a` + `g7` → `("select", "g7")`;
  - pick `t5a` + `o2-3` → `("select", None)`.

  **`fairness`.** Each assertion checks text and ok/chip exactly:
  - a fresh 4-team flight → lines "Games this week" `"2 each"` ok, "Season total" `"8 each"` ok, "Pairs meeting" `pair_meet_text(...)` ok, "Longest sit" ok;
  - a 5-team flight with games 2 → week counts of 2 and 1 still `ok=True`;
  - a manually moved schedule where one team sits 2 rounds → "Longest sit" `ok=False`, `chip="{team} · 2 rounds"`;
  - season totals 6 and 9 → `ok=False`, text `"6–9 per team"`, chip naming the lowest and highest teams;
  - withdrawn teams are excluded;
  - `flight_ids={x}` returns only that flight.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_preview_data.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** Fairness rules:
  - **Games this week:** each active team's count == `games_per_team_by_week[week-1]`. In a flight with an odd number of active teams, a count one lower is also allowed. ok text: `"{g} each"` or `"{g-1}–{g} each"`. Off text: `"{team} {n}, …"` for the off-plan teams.
  - **Season total:** ok when max − min ≤ 1. Text `"{n} each"` or `"{lo}–{hi} each"`. Off: `"{lo}–{hi} per team"`, chip `"{lo_team} {lo} · {hi_team} {hi}"`.
  - **Pairs meeting:** among active teams. ok when the spread ≤ 1. Text from `pair_meet_text`.
  - **Longest sit:** the max over active teams of `report.longest_sit[week]`. Ok when ≤ 1, text `"{n} round(s)"` (or `"none"` for 0). Off: chip `"{team} · {n} rounds"`, where the first team in flight order wins ties.

- [ ] **Step 4: Run** the full suite. Expected: PASS (including the existing `summary_line` tests).

- [ ] **Step 5: Commit** `feat(league): preview board, click rules and fairness lines`

---

### Task 4: The Preview page (read-only), routing, row link

**Files:**
- Create: `league/preview_views.py`, `templates/league/preview/page.html`, `templates/league/preview/_board.html`, `templates/league/preview/_tile.html`, `templates/league/preview/_fairness.html`
- Modify: `league/urls.py` (add `events/<int:pk>/preview/` → `event_preview`), `league/views.py:_row_link`
- Test: `tests/test_preview_page.py`

**Interfaces:**
- Consumes: `parse_state`, `build_board`, `fairness` (Task 3).
- Produces: `preview_event(request, pk) -> Event` (the access rule from Global Constraints) and `render_preview(request, event, state, *, conflict: dict | None = None, confirm: str | None = None, status=200) -> HttpResponse`. `render_preview` renders `_board.html` (board + fairness) when `HX-Request` is set, otherwise `page.html`. Context keys: `event`, `board`, `fairness`, `conflict` (`{"key": tile_key, "message": str}`), `confirm` (`"regenerate"`/`"publish"`/None), `has_matches`, `query` (the state minus pick, url-encoded, for links).

- [ ] **Step 1: Write the failing tests.**
  - **Access:**
    - `test_access`: admin 200. Player (`User` with `is_admin=False`) → 403. Anonymous → login redirect. Another org's event → 404.
  - **Page content:**
    - `test_page_shows_week_grid`: the seeded 4-team league shows "Draft · not visible to players", tabs "Week 1"…"Week 4", "Round 1", "Court 1", team names, and the `data-level` division bar.
    - `test_open_court_and_cancelled_tiles`: a court-3 event shows "Open court". A `CANCELLED` match shows "Cancelled".
    - `test_filters_fade_other_flights`: with two flights and `?flight=<pk>`, the other flight's tiles have `data-faded` and no `href`/`<form>` inside them, and the fairness panel lists only the chosen flight.
    - `test_division_narrows_flight_select`: `?division=advanced` → the Flight `<select>` lists only Advanced flights.
    - `test_junk_params_render`: the Review Focus 2 values all return 200 with Week 1 selected.
    - `test_empty_state`: no matches → "No schedule yet" and a link to `event_setup_step … 'games'`.
    - `test_stale_banner`: `schedule_stale=True` → "Inputs changed — regenerate to apply them."
    - `test_published_badge`: published → "Published", and no Publish button.
  - **Routing:**
    - `test_row_link`: My Events links a published event to `/events/<pk>/preview/` (no `event_schedule` yet).
    - Generate now redirects to the preview: update the slice-2 test that expected `event_list`, if one asserts it.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_preview_page.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **`event_preview` GET:** `state = parse_state(...)`, then `render_preview`.
  - **`page.html`** extends `base_app.html`. It has the header (name, badge, Regenerate/Publish forms — they post to the Task 6 URLs; render them now), the stale banner, and `<div id="preview-board">{% include "league/preview/_board.html" %}</div>`.
  - **`_board.html`:**
    - The week tabs (segmented) as links carrying the filters.
    - Division and Flight `<select>`s in a GET form, with `hx-get` + `hx-target="#preview-board"` + `hx-push-url="true"` and `hx-trigger="change"`, plus a submit button for no-JS.
    - The grid in an `overflow-x-auto` card, with a sticky first column for the round labels.
    - "No games this week" when `rows` is empty.
    - The fairness include.
  - **`_tile.html`** renders the four kinds. Read-only for now: no links. Task 5 adds them.
  - **`_row_link`:** for non-draft events, return `optional_reverse("event_schedule", pk) or optional_reverse("event_preview", pk)`.

- [ ] **Step 4: Run** the full suite and `manage.py tailwind build`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(league): Schedule Preview page with week grid, filters and fairness`

---

### Task 5: Pick and act (swap games, swap teams, move)

**Files:**
- Modify: `league/preview_views.py` (add `event_preview_edit`), `league/urls.py` (`events/<int:pk>/preview/edit/` → `event_preview_edit`), `templates/league/preview/_tile.html`
- Test: `tests/test_preview_edit.py`

**Interfaces:**
- Consumes: `resolve_click` (Task 3); `swap_games`, `swap_teams`, `move_game`, `EditRefused` (Task 2); `render_preview` (Task 4).
- Produces: POST `event_preview_edit` with fields `pick`, `target`, `week`, `division`, `flight`.

- [ ] **Step 1: Write the failing tests.**
  - **Clickable tiles:**
    - `test_select_links`: with no pick, every unlocked, unfaded game tile has a link whose query has `pick=g<id>`, and each team name has `pick=t<id>a|b`. Open tiles aren't clickable.
    - `test_picked_tile_marked`: `?pick=g<id>` → that tile has `data-selected`. The other game tiles and the open tiles are now `<form method="post" action=".../preview/edit/">` with hidden `pick` and `target`. Clicking the picked tile again links to the URL without `pick`.
    - `test_locked_tiles_not_clickable`: scored, withdrawn and cancelled tiles have no link or form, even with a pick.
  - **Acting:**
    - `test_swap_games_post`: no-JS POST → 302 to the preview with the same week and filters and no pick. The rows are swapped.
    - With `HX-Request` → 200, the `_board.html` partial (no `<html>`), and an `HX-Push-Url` header without `pick`.
    - `test_move_post` and `test_swap_teams_post`: the same checks, one for each.
  - **Conflicts:**
    - `test_conflict_renders_on_target`: a clashing swap → 200. The target tile has `data-conflict` and shows the engine's message, nothing changed, and there's no pick.
    - `test_stale_pick`: `pick=g999999` → 200 with "That game is no longer on the schedule. Refresh and try again."
  - **Access:** another org → 404. A GET on the edit URL → 405.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_preview_edit.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **`_tile.html`:** each clickable element looks up its action in `tile.actions` (built in Task 3), so the template stays logic-free.
    - `"select"` → `<a href="?{query}&pick=…" hx-get hx-target="#preview-board" hx-push-url="true">`.
    - Any write action → a `<form method="post" action="{% url 'event_preview_edit' %}" hx-post hx-target="#preview-board">` with a button.
    - The game area and the team names are separate controls, never nested.
  - **`event_preview_edit`:**
    1. Re-parse the state from POST.
    2. `action, value = resolve_click(board, target)`.
    3. Write actions call the bridge (decode `g<id>` / `t<id><side>` / `o<r>-<c>`). A `"select"` result just re-renders.
    4. On success: HTMX → render the board with `HX-Push-Url`; no-JS → redirect.
    5. On `EditRefused`: render with `conflict={"key": target, "message": str(exc)}`, status 200.

- [ ] **Step 4: Run** the full suite and `tailwind build`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(league): pick-and-act swaps and moves on the Schedule Preview`

---

### Task 6: Regenerate and Publish

**Files:**
- Modify: `league/preview_views.py` (add `event_preview_regenerate`, `event_preview_publish`), `league/urls.py` (`…/preview/regenerate/`, `…/preview/publish/`), `templates/league/preview/page.html`
- Test: `tests/test_preview_publish.py`

**Interfaces:**
- Consumes: `regenerate`, `publish`, `EditRefused` (Task 2); `render_preview(..., confirm=…)` (Task 4).

- [ ] **Step 1: Write the failing tests.**
  - **Regenerate:**
    - `test_regenerate_asks_first`: a POST without `confirm` → 200 with "Regenerate the schedule? This replaces every game, including your swaps and moves." The matches are unchanged.
    - On a published event, it also shows "Players have already seen this schedule."
    - `test_regenerate_confirmed`: `confirm=1` → 302 to the preview with the toast "Schedule regenerated · {n} games over {w} weeks". The matches are new (compare ids), and stale is cleared.
    - `test_regenerate_blocked`: a scored event → the existing A13 message as an error toast, nothing changed. A blocker → the blocker text as an error toast.
  - **Publish:**
    - `test_publish_asks_first`: "Publish Spring Tuesday League? Players will be able to see the schedule."
    - `test_publish_confirmed`: 302 to `event_list` (no `event_schedule`) with "Spring Tuesday League published", and the status is published.
    - `test_publish_disabled_when_stale`: the page shows the button `disabled` and "Regenerate first: inputs changed since this schedule was made.". A forced POST with `confirm=1` is refused with that toast.
    - `test_publish_no_matches`: "Generate a schedule before publishing."
  - **Access:** another org → 404 on both URLs. A player → 403.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_preview_publish.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - Both views are `@require_POST`. Without `confirm=1`, they re-render via `render_preview(confirm="regenerate"|"publish")`. The amber alert's confirm button posts `confirm=1`, and the cancel link goes back to the preview.
  - Publish redirects to `optional_reverse("event_schedule", pk) or reverse("event_list")`.

- [ ] **Step 4: Run** the full suite and `tailwind build`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(league): regenerate and publish from the Schedule Preview`

---

### Task 7: Wizard changes: renames aren't stale, published warnings

**Files:**
- Modify: `league/setup_forms.py` (`TeamForm.save` records `self.roster_changed: bool`), `league/setup_views.py` (`teams_step` calls `mark_stale` only when `form.roster_changed`; `event_team_delete` adds a confirm on published events; the flight-removal copy), `templates/league/setup/_frame.html` (banner), `templates/league/setup/games.html` (confirm text), `templates/league/setup/teams.html` or `_team_list.html` (delete confirm alert)
- Test: `tests/test_setup_published.py`

**Interfaces:**
- Produces: `TeamForm.roster_changed`. True for a new team or a changed set of player pks; False for a name-only edit.

- [ ] **Step 1: Write the failing tests.**
  - **Stale rules:**
    - `test_rename_does_not_mark_stale`: generate, then edit a team's name only → `schedule_stale` stays False.
    - `test_player_change_marks_stale`: change one player → True.
    - `test_new_team_marks_stale`: add a team → True.
  - **Published warnings:**
    - `test_published_banner_on_every_step`: a published event shows the Global Constraints banner on all five steps. A draft doesn't.
    - `test_generate_confirm_mentions_players`: published + matches → the regenerate confirm includes "Players have already seen this schedule."
  - **Team delete:**
    - `test_published_team_delete_asks_first`: a POST without `confirm` → the team still exists, and the teams page shows "Delete {team}? This also removes {flight}'s games from the published schedule. Regenerate to rebuild them." with a confirm button.
    - With `confirm=1`, the team is deleted.
    - A draft deletes in one click as today.
  - **Flight removal:** `test_published_flight_removal_copy`: the removal confirm has the extra sentence.

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/test_setup_published.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement.** For the delete confirm on a published event, a POST without `confirm=1` redirects to `…/setup/teams/?flight=<pk>&delete=<team_pk>`. The teams page renders the amber confirm alert for that team, with a form posting `confirm=1` to `event_team_delete` and a cancel link.

- [ ] **Step 4: Run** the full suite. Expected: PASS.

- [ ] **Step 5: Commit** `feat(league): renames don't stale the schedule; warn when editing a published league`

---

### Task 8: End-to-end walk-through, screen check, README

**Files:**
- Test: `tests/test_preview_flow.py`
- Modify: `README.md`

- [ ] **Step 1: Write the flow test** `test_generate_edit_publish`. Through the test client, as admin:
  1. Build the demo-sized league in the wizard (or with factories plus `generate_event`), with `courts=3` so open courts exist.
  2. GET the preview.
  3. Pick and swap two games.
  4. Pick and swap two teams.
  5. Move a game into an open court.
  6. Attempt a clashing swap and see the message.
  7. Publish (confirm).
  8. Assert the status is published, My Events links the row to the preview, and the setup step shows the published banner.

- [ ] **Step 2: Run** it, then the full suite. Expected: PASS.

- [ ] **Step 3: Screen check at 390px and 1280px.**
  - **Setup:** run `manage.py tailwind build`, `migrate`, `seed_demo --reset`, then `runserver`. Log in as `admin@example.com` / `pickleball`.
  - **Capture:** the preview for the seeded draft league:
    - Week 1;
    - a picked tile;
    - a conflict;
    - an open court and a move;
    - the filters;
    - the regenerate and publish confirms;
    - a published league's wizard banner.
  - **Check on each screen:**
    - `document.documentElement.scrollWidth <= window.innerWidth`;
    - the grid scrolls inside its card with the round labels pinned;
    - clicks swap the board without a page reload.
  - Save the screenshots in the session scratchpad. Fix anything that's off and re-run the suite.

- [ ] **Step 4: README.** Add a "Review and publish a schedule" section:
  - the preview URL;
  - swap games or teams and move into open courts (clashes are refused);
  - the fairness panel;
  - Regenerate replaces everything;
  - Publish is blocked while inputs have changed;
  - a published league can still be edited in setup, with warnings.

- [ ] **Step 5: Commit** `test(league): end-to-end preview walk-through; README for reviewing and publishing`
