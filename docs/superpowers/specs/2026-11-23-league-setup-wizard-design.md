# Slice 2 — League setup wizard (P3) design

**Status:** approved by owner · 2026-11-23
**Builds on:** PRD §4 Flow A steps 1–6, §5 P3, §8 A13; front-end spec §8 slice 2; slice 1 (frame, auth, My Events).

## 1. Intent

The league director creates a league and gets a schedule without help. P3 is the first half of the north-star flow (Flow A). She clicks "+ Create" on My Events, fills in five short steps, and clicks Generate. Every step saves to the database, so she can stop at any point and pick it up later from My Events.

Success: starting from an empty org, she can create the demo-sized league (two flights, four teams each, four weeks, default plans) and generate a draft schedule. She never sees the Django admin and never meets a dead end.

## 2. Goals, non-goals, anti-goals

**Goals**
- `/events/new/` and `/events/<id>/setup/<step>/`, with five steps: Basics, Scoring, Flights, Teams, Games plan.
- A draft is saved after every step. Draft events on My Events link back into setup.
- Step 5 shows a live per-flight summary and notes taken straight from the scheduler. Its **Generate schedule** button really generates and saves matches.
- The A13 guard. Once any score exists, schedule inputs can't change, in the wizard or through `Event.set_week_count`.

**Non-goals (other slices)**
- P4 Schedule Preview, swaps, and publish (slices 3–4). Invites going out on publish.
- The tournament version and the fit check (slice 8).
- Editing or cancelling single weeks, or moving a week's date.
- A full Players directory (P9). Step 4 only creates and picks players.

**Anti-goals**
- Losing anything she typed. An unsaved step must never vanish just because she clicked a different step.
- An error that doesn't name what to fix. Every block names the flight, team, or week.
- A screen that only works with JavaScript. Every step works as a plain form post.

## 3. Approaches considered

| Approach | Trade-off | Verdict |
| --- | --- | --- |
| **One URL and Django form per step, saved to the DB on submit, with HTMX for the in-place parts** | Matches the stack picked in the front-end spec. Drafts are real rows. Works without JS. A few more views. | **Picked** (owner agreed) |
| `django-formtools` SessionWizardView | Keeps answers in the session until the last step. That breaks "save a draft after every step" and resuming from My Events. | Rejected |
| A single JS-driven page | Needs a JS framework the project doesn't use. Fights the per-step save and the no-JS fallback. | Rejected |

**What Generate does before P4 exists (owner picked option A):** Generate runs `generate_event` for real. On success it redirects to `event_preview` if that URL exists (`optional_reverse`). Otherwise it goes to My Events with the toast "Schedule drafted · 16 games over 4 weeks". When slice 3 adds `event_preview`, the redirect switches over on its own.

## 4. Design

### 4.1 Routes and access

| URL | Name | What it does |
| --- | --- | --- |
| `/events/new/` | `event_create` | Step 1 for a new event. The Event row (type League, status Draft) is created on the first valid submit. |
| `/events/<id>/setup/` | `event_setup` | Redirects to the first unfinished step, or to step 5 when every step is done. |
| `/events/<id>/setup/<step>/` | `event_setup_step` | `step` ∈ `basics`, `scoring`, `flights`, `teams`, `games`. |
| `/events/<id>/setup/games/generate/` | `event_generate` | POST only. |
| `/events/<id>/setup/teams/players/` | `player_search` | GET, for the HTMX type-ahead. Returns matching players in the admin's org. |

- Every view uses `@admin_required`. The event is looked up within `request.user.organization`. An event in another org, or a tournament event, returns 404. *My call: tournaments get a 404 until slice 8.*
- My Events: `event_create` already powers the "+ Create" button (slice 1 template). A Draft row with no matches now links to `event_setup`. A draft that has matches links to `event_preview` once that exists, and to `event_setup` until then.

### 4.2 Frame and stepper

- Uses `base_app.html`. The page title is "Create league" or "Edit league · <name>".
- The stepper component from the spec shows numbered steps 1–5 in done / current / upcoming states, with a Back / Next footer. On a phone it collapses to "Step 3 of 5 · Flights".
- **Free navigation** *(my call)*: once the event exists, every step label is a link. "Done" means the step's data is valid:
  - Basics and Scoring: saved.
  - Flights: at least one flight.
  - Teams: every flight has at least 2 teams and every team has 2 players.
  - Games plan: every flight's grid matches the week count.
- **Next** saves and moves on. **Back** saves and moves back. Both submit the form, so nothing is lost. If the form is invalid it re-renders with errors and doesn't move.
- On step 1 for a new event, Back is "Cancel" and returns to My Events. Nothing has been saved at that point.

### 4.3 Steps

**1 · Basics.** Name, start date, number of weeks (1–20, *my call*), and number of courts (1–20, *my call*). Type is fixed to League (hidden).
- Saving calls `set_week_count(n)`. It also rewrites every week's date to `start_date + 7·(n−1)`. Today's `set_week_count` only dates new weeks, so the plan must fix that.
- If the week count changes, each flight's grid is resized (see 4.4).

**2 · Scoring.** Match format (1 game / best of 3 / best of 5), points to win (11/15/21), win by 2 (on/off), player score entry (on/off). Defaults come from the model.

**3 · Flights.** A 3×3 checkbox grid: rows Beginner / Intermediate / Advanced, columns Men's / Women's / Mixed. Ticking a cell creates the Division (if needed) and the Flight. Unticking removes it.
- Unticking a flight that has teams needs a confirm step: "Removing Intermediate Mixed deletes its 4 teams." It's a second submit with a confirm flag, not a JS dialog. Empty divisions are deleted too.
- At least one flight is needed to count as done. Next with nothing ticked shows "Pick at least one flight."

**4 · Teams.** A flight switcher on the left (a select on a phone) and the chosen flight's team list on the right.
- "+ Add team" opens an inline row (HTMX swap; without JS it's a full form page) with three fields: team name, Player 1, and Player 2.
- Each player field is a type-ahead over the org's players (`player_search`, by name or email, 10 results). The last option is "+ New player", which shows name and email (email optional) for a new Player in the org.
- Teams can be renamed, have players changed, and be deleted.
- Validation:
  - The team name is unique in the flight.
  - The two players are different.
  - A player can't be on two teams in the same flight: "Sam Lee is already on Dinkers in this flight." Being in two different flights is allowed, and the scheduler handles clashes between flights.
  - A new player's email can't match an existing player in the org. The error offers that player instead.
- This step doesn't block Next. A flight with fewer than 2 teams, or a team missing a player, shows an amber note, and Generate blocks on it later (4.5).

**5 · Games plan.** One card per flight, showing the flight name and team count.
- The plan is a radio choice: "Each team plays every other team: once / twice / custom".
  - Once / twice: the grid is filled from `scheduler.round_robin_preset(teams, weeks, times)` and is read-only.
  - Custom: the grid is editable, with one whole-number input per week.
  - The total per team shows at the end of the row.
- **Default plan** *(my call)*: a new flight starts on the first of *once* / *twice* that fills every week. If neither fits (more weeks than a double round robin has games), it starts on *custom* with 1 game per team every week. For the demo league (4 teams, 4 weeks), "once" is only 3 games, so it opens on *twice*: 6 games per team, spread 2, 2, 1, 1.
- **Live summary** *(my call, event-wide)*: league night shares courts across flights, so the dry run is `scheduler.generate` over **every flight in the event** with the form's unsaved values swapped in for the flight being edited. Nothing is saved. Each card shows its own flight's `summary_line`. Inputs re-post the whole step 5 form via HTMX (`hx-trigger="change"`) and the whole list of cards is swapped, so every card stays in step.
- Notes under the summary. The scheduler has no note text, so these are new helpers in `league/scheduling.py` (or a small `scheduler` addition) worked out from the dry-run schedule:
  - **Odd team count** (PRD wording): "5 teams: one team sits out each round, so each week one team plays 1 fewer. Byes rotate."
  - **Long night** *(my call on the trigger)*: shown for each week where the shared night needs more rounds than the most games any team in this flight plays that week, so some teams sit out a round. The text follows the PRD pattern: "Week 2: each team plays 3 games. On 2 courts that takes 4 rounds." It's informational and doesn't block.
  - **Preset error** "Week 4 has no games — reduce weeks or choose twice". This one blocks Generate.
- Withdrawn teams (`withdrawn_at` set) are left out of every count, preset, and check on steps 4–5, matching `event_flights`. The wizard can't withdraw teams. *My call.*
- With no JS, an "Update summary" button posts the form.
- A flight with fewer than 2 teams shows "Add at least 2 teams to Intermediate Mixed before generating." instead of a grid.
- Footer: Back · **Generate schedule**. If matches already exist, the button says **Regenerate schedule**. It goes through a confirm step first: "Regenerating replaces the current draft schedule."

### 4.4 Data changes

- **New `Flight.games_plan`** field: `once` / `twice` / `custom`. The model default is `once`, but new flights get the default described in 4.3. A migration is needed.
- A once/twice grid is recomputed from the team count and week count whenever either changes (saves on steps 1, 3 and 4). **If the preset can't be computed** (fewer than 2 teams, or `round_robin_preset` raises), the save still goes through and `games_per_team_by_week` is stored as `[]` *(my call)*. Step 5 then shows the preset's own message, or "Add at least 2 teams…". Generate runs the same preset check before `_check_ready`, so the PRD message appears instead of a length mismatch. The Games plan step counts as done only when every flight's list has one entry per week.
- When the week count changes on a **custom** grid, it's truncated, or padded with `0` for the new weeks. Step 5 then highlights those weeks for review. *My call.*
- **New `Event.schedule_stale`** boolean, default False. It's set True when any input on steps 1, 3, 4 or 5 is saved while matches exist, and set False by `generate_event`. Step 5 shows "You changed the setup since the schedule was made. Regenerate to apply it." (P4 will reuse the flag for its own "Inputs changed" warning.) *My call.*
- **New `Event.has_scores()`** method, moved out of `scheduling._check_ready`. It's true if any match in the event is Final, has a forfeit, or has a GameScore row. `_check_ready` calls it.

### 4.5 Generate

`event_generate` (POST) calls `generate_event(event)` inside the existing transaction.
- On `ScheduleError` it re-renders step 5 with the message at the top. The messages already name the flight or team.
- On success: `schedule_stale = False`, a toast "Schedule drafted · <N> games over <W> weeks", then a redirect as described in §3.
- Status stays Draft. Publish is slice 4.

### 4.6 A13 guard (carry-forward)

- `Event.set_week_count` raises `ValidationError` if `has_scores()` is true: "Scores have been entered, so the weeks can't change."
- Once `has_scores()` is true, every wizard save view refuses POSTs. Steps render read-only with the banner "Scores have been entered, so the setup is locked. Individual games can still be moved." The only fields still editable are **name** and **player score entry**, since neither affects the schedule. *My call.*
- The check runs inside `transaction.atomic()` with `select_for_update()` on the Event row, so a score can't land between the check and the write. (The score-entry slice adds the matching lock on its side.)
- **Deleting a flight** removes its matches by cascade (`Match.flight` is CASCADE).
- **Deleting a team while a draft schedule exists** is different. `Match.team_a` / `team_b` are `RESTRICT`, and nothing cascades from Team to Match, so a plain delete would raise `RestrictedError`. *My call:* in one transaction, the view first deletes **all of that flight's matches**, then the team, and sets `schedule_stale`. The flight shows as unscheduled until she regenerates. That's simpler than leaving a schedule with holes in it, and regenerating is the only way the PRD allows team changes anyway. Swapping a player on an existing team doesn't touch matches. It only sets `schedule_stale`.
- Any other `RestrictedError` (not `ProtectedError`) is caught and shown as a message. It must never 500.

## 5. Constraints

- Stack: Django + Basecoat/Tailwind + HTMX 2.0.11 (vendored). No new JS framework.
- Reuse the slice-1 components: `form_field`, `form_errors`, `empty_state`, `error_state`, and toasts through Django messages.
- Laptop-first, but usable at 390px.
- All rows are scoped to the admin's organization.

## 6. Testing

- View tests per step: GET renders, a valid POST saves and redirects, an invalid POST shows errors, another org gets 404, a player gets 403.
- Week-count change: weeks are added/removed and re-dated, and grids are recomputed or padded.
- Flights: untick with teams → confirm → cascade.
- Teams: each validation rule above. New-player email clash.
- Games plan: preset fill, preset error, custom save, and the live summary partial.
- Generate: success → toast + redirect to My Events (no `event_preview` yet). ScheduleError → message on step 5. Regenerate replaces matches and clears `schedule_stale`.
- A13: with a GameScore present, `set_week_count` raises and every step POST is refused except name / score-entry.
- A screenshot check of each step at 390px and 1280px.

## 7. Left to the builder

- Template and partial layout, and HTMX target names.
- Whether the step views are function views or one small class with a per-step form.
- Type-ahead details: debounce, and the empty-result text.
- The exact wording of amber notes not quoted from the PRD.
