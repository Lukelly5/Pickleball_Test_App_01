# Slice 3: Schedule Preview (P4) design

**Status:** approved by owner · 2026-11-23
**Builds on:** PRD §4 Flow A steps 6–7, §4 "After publish", §5 P4. Front-end spec §5 (match tile, fairness panel, tabs) and §7 (P4 mockup). Slice 2 (setup wizard, Generate).

## 1. Intent

After she clicks **Generate** in the wizard, the league director lands here. She checks the draft schedule one week at a time and fixes anything she doesn't like by swapping or moving games. The fairness panel shows that the schedule is even. Then she publishes. This is the PRD's north-star screen.

Success: starting from the demo league (2 flights, 4 teams each, 4 weeks), she can generate, look through every week, swap two games, swap two teams, move a game into an open court, see a clash get refused with a clear message, and publish. She never needs the Django admin.

## 2. Goals, non-goals, anti-goals

**Goals**
- `/events/<id>/preview/` (URL name `event_preview`), for admins only and scoped to her organization.
- Week tabs, plus Division and Flight filters. The grid shows rounds as rows and courts as columns.
- Three edits, each with a clash check:
  - **Swap games:** two games trade slots.
  - **Swap teams:** two team names trade places, within one flight.
  - **Move a game into an open court:** new in this slice; the owner picked it.
- A fairness panel under the grid.
- **Regenerate** and **Publish**.
- The "Inputs changed — regenerate to apply them" warning.
- Once an event is published, the setup wizard still works, but it warns her first (the owner picked this).

**Non-goals (later slices)**
- P5 Schedule / Tonight, the share link, and player-facing views (slice 4).
- Score entry (slice 5).
- Emails or invites sent on publish. Players simply see the schedule once the pages that show it exist.
- Round start times. The mockup shows "6:30", but no start time is stored anywhere, so rounds are labelled "Round 1", "Round 2", and so on.
- Unpublishing.
- Tournaments. A tournament's matches use the same tables, so the page should work for them too, but nothing tournament-specific is built here.

**Anti-goals**
- A clash that gets saved. Every edit is checked on the server, inside a transaction, before anything is written.
- Losing her swaps or her published schedule without warning. Regenerate always asks first and says what will be replaced.
- Moving or swapping a game that already has a score.
- A page that scrolls sideways on a phone. The grid scrolls inside its own box instead.

## 3. Approaches considered

**Moving into an empty slot (owner picked B)**

| Option | Trade-off | Verdict |
| --- | --- | --- |
| A. Swap only; open courts can't be selected | Uses the existing engine as-is. She can't pull a game into an earlier round. | Rejected |
| **B. Swaps plus moving a game into an open court** | More flexible. Needs a new `move_game` step in the engine with the same clash check. | **Picked** |

**After publish, the setup wizard (owner picked "allow with a warning")**

| Option | Trade-off | Verdict |
| --- | --- | --- |
| Lock the wizard after publish | Safest, but she can't fix a team's name or players after publishing. | Rejected |
| **Allow it, with a warning** | She keeps full control until scores exist (the existing A13 lock). Warnings say when a change will replace what players can already see. | **Picked** |
| Allow it with no change | A published schedule can be wiped silently. | Rejected |

**How the clicking works (owner picked A)**

| Option | Trade-off | Verdict |
| --- | --- | --- |
| **A. The server tracks the selection.** Each tile is an HTMX request, and the pick lives in the URL. | Same approach as the rest of the app: HTMX only, no custom JS. Fully testable with the Django test client. A refresh keeps her place. The highlight costs one quick round-trip. | **Picked** |
| B. A small JS file handles the highlight | The highlight is instant, but it adds the app's first custom JS file and a second place to test. | Rejected |
| C. Drag and drop (SortableJS) | Feels natural on a laptop, but it's awkward on a phone, a poor fit for swapping team names, and adds a new library. | Rejected |

## 4. The page

```
Spring Tuesday League  [DRAFT · not visible to players]     [↻ Regenerate] [Publish]
⚠ Inputs changed — regenerate to apply them.                (only when schedule_stale)
( Week 1 | Week 2 | Week 3 | Week 4 )          [Division: All ▾] [Flight: All ▾]
            Court 1         Court 2          Court 3
Round 1     ▌Dinkers        ▌Lobsters        ▌Volley Llamas
            ▌Smashers       ▌Kitchen Kings   ▌Net Gains
Round 2     ▌Dinkers        ┆Open court┆     ┆Open court┆
            ▌Lobsters
┌ Fairness · Week 1 ──────────────────────────────────────────────────────┐
│ Games this week: 2 each ✓   Season total: 8 each ✓                        │
│ Pairs meeting: every pair 2–3 times ✓   Longest sit: [Big Dill · 2 rounds] │
└────────────────────────────────────────────────────────────────────────┘
```

- **Header:** the event name and a status badge. A draft shows "Draft · not visible to players". A published event shows "Published" (both badges come from the design-system spec).
- **Week tabs** use the segmented-tab component. The page opens on Week 1. The chosen week is kept in `?week=`.
- **Grid:**
  - One row per round, from Round 1 up to the highest round that has a game that week.
  - One column per court, from 1 to `event.courts`.
  - Every round/court cell that has no game is an **Open court** tile (dashed outline).
  - Each game tile shows the flight's division color bar, an uppercase meta line with the flight name, and the two team names as separate click targets.
- **Filters:** Division and Flight dropdowns, kept in `?division=` and `?flight=`. Games outside the filter stay in place as faded, unclickable tiles, so a busy court never looks open. Picking a division narrows the Flight dropdown.
- **Phone:** the grid scrolls sideways inside its card, and the round labels stay pinned on the left. The header buttons wrap.
- **Empty state:** if the event has no matches, the page says "No schedule yet" and links to the wizard's Games step.

## 5. Editing: pick, then act

The pick lives in the URL as `?pick=g<match_id>` for a game or `?pick=t<match_id>a` / `t<match_id>b` for a team name. Every click is an HTMX request that redraws the grid and fairness section, with `hx-push-url` so Back and refresh behave.

| First click | Second click | Result |
| --- | --- | --- |
| A game | Another game, same week | **Swap games** (both slots trade) |
| A game | An open court, same week | **Move game** to that round/court |
| A team name | Another team name, same flight | **Swap teams** (the two teams trade places) |
| Anything | The same thing again | Un-pick |
| A team name | A game area or open court | The pick switches to the new thing (no action) |
| A game | A team name | Treated as clicking that team's game (swap games) |

- Selecting is a GET that only changes `pick`. Acting is a POST to `/events/<id>/preview/edit/` with `pick`, `target`, and the current `week/division/flight`. It returns the redrawn grid, or the full page when HTMX isn't present. Without JS, tiles are plain links (select) and a small form (act), so it still works as full-page loads.
- The picked tile gets the selected style: Cobalt outline and a tint.
- **Conflicts:** the server refuses the edit, nothing changes, and the redrawn grid shows the target tile with a red outline and the engine's message. The pick is cleared. Messages:
  - Swap: the existing ones ("Can't swap: Smashers would play on Court 1 and Court 3 in Round 2.", "Can't swap: teams can only play teams in their own flight.").
  - Move: same wording with "Can't move:".
- **Scored games:** a game that is final, forfeited, or has any game score can't be picked, moved, swapped into, or have its teams swapped. Its tile shows the score state and isn't clickable. Before publish no game has scores, so this only matters for published events.
- **Success:** the grid redraws with the change. No toast; the change on the grid is the confirmation.
- **Swap teams inside one game** (team A and team B of the same game) just flips the sides. It's allowed and harmless (the engine already supports it).

### Engine and bridge

- **Engine (`scheduler/swap.py`):** add `move_game(schedule, slot, target)`.
  - `target` is a `(week, round, court)` slot that must be empty and in the same week.
  - Its round must be 1 through the highest round that week. A move can't create a new round.
  - Its court must be 1 through `schedule.courts`.
  - The clash check reuses `_check_week`, with the verb passed in so the message says "Can't move:".
- **Bridge (`league/scheduling.py`):** add `swap_games`, `swap_teams`, and `move_game` functions that work on `Match` rows. Each one:
  - takes the event row lock (`select_for_update`, as `generate_event` does, per the carry-forward note),
  - refuses scored games,
  - loads the schedule with `load_schedule`, runs the engine function as the check, and writes only the changed rows.
- **Unique constraint:** swapping two games' slots runs into the `(week, round, court)` unique constraint, so write it in two steps: park one row on a spare court number first. Courts must be ≥ 1 (`match_court_positive`), so the spare must be above `event.courts`. The builder picks the exact mechanism.
- Edits don't set `schedule_stale`, because they don't change any inputs.

### Games and weeks the engine doesn't see (my calls)

- **Cancelled and void games:** `load_schedule` skips them, but they still hold their slot under the unique constraint.
  - They're drawn as faded "Cancelled" tiles, not open courts. They can't be picked, and nothing can be moved into them.
  - The bridge checks that a move's target slot has no `Match` row of any status before writing.
  - Nothing in the app creates these statuses yet (only the Django admin can), so this is a guard, not a feature.
- **Cancelled weeks** (`Week.Status.CANCELLED`) keep their tab, labelled "Week 3 · Cancelled", and the grid is read-only. Nothing creates these yet either.
- **Withdrawn teams:** their games show on the grid with a "Withdrawn" badge on the team name.
  - They can't be picked, and the other team in the game can't be swapped out. Withdrawal turns those games into forfeits in a later slice, so moving them around now has no point.
  - They're left out of the fairness panel's counts.
  - `fairness_report` is called with the flights including withdrawn teams (`event_flights(event, include_withdrawn=True)`, as `load_schedule` already does) to avoid a `KeyError`. The panel then shows only active teams.

## 6. Fairness panel

This uses `scheduler.fairness_report` for the event's active teams, limited to the filtered flights. Each line ends in ✓ when even, or shows an amber chip when not.

- **Games this week:** each team's game count this week. Even means every team plays its flight's planned count for that week (`games_per_team_by_week`). In a flight with an odd number of teams, a team may play 1 fewer because of the rotating bye, and that still counts as even. Anything else is amber, naming the teams and counts.
- **Season total:** total games per team across all weeks. In each flight, it's even when every active team's total is within 1 of the others, and amber otherwise, naming the teams and totals (my call). Rotating byes in odd-sized flights keep totals within 1 over a season. A wider spread means a swap or move unbalanced things.
- **Pairs meeting:** per flight, how many times each pair meets (reusing `summary_line`'s wording). Amber when the spread is more than 1.
- **Longest sit:** each team's longest gap between games that night, in rounds. Amber chip for any sit over 1 round, naming the team ("Big Dill · 2 rounds").

With "All flights", the panel shows one block per flight.

## 7. Regenerate and Publish

- **Regenerate:** opens a Basecoat confirm dialog (not a browser `confirm()`): "Regenerate the schedule? This replaces every game, including your swaps and moves." When the event is published, it adds: "Players have already seen this schedule." Confirming runs the same blocker check the Games step uses (`plan_views` → first `blocker`), then calls `generate_event` directly with the saved inputs. It doesn't go through `event_generate`, which expects the posted Games form. Then it redraws the preview with a toast ("Schedule regenerated · 16 games over 4 weeks"). A blocker or `ScheduleError` shows as an error toast and nothing changes. It's blocked once scores exist (the existing A13 rule and message).
- **Publish:** shown only on drafts.
  - A confirm dialog: "Publish Spring Tuesday League? Players will be able to see the schedule."
  - On confirm, set `status=published` and redirect to `event_schedule` if it exists (`optional_reverse`), otherwise to My Events with the toast "Spring Tuesday League published".
  - **Blocked while `schedule_stale`** (my call; publishing an out-of-date schedule is the failure to avoid): the button is disabled, with the note "Regenerate first: inputs changed since this schedule was made."
  - Blocked when there are no matches.
  - **Owner's call (option A):** the block stays, but renaming a team no longer sets `schedule_stale` (see §8). A rename shows on the schedule immediately because games point at the team row, so it never needs a regenerate.
- **"Inputs changed" banner:** shown whenever `event.schedule_stale` is true, with a Regenerate button. The wizard already sets the flag.

## 8. Wizard changes: stale rules and after-publish warnings

**Renames no longer mark the schedule stale (owner picked A).**
- In `teams_step`, a team save calls `mark_stale` only when something the scheduler uses changed:
  - a new team,
  - a change to the team's players.
- A save that only changes the name doesn't call it.
- Adding or removing teams, and changing players, weeks, flights or the games plan, still mark it stale as today.
- Player changes stay in the list because they can create a real clash in the saved schedule. For example, a player who's now on teams in two flights could be playing in the same round twice.

**After publish: warn, don't lock (owner's call).** When `event.status` isn't draft:
- **Every setup step** shows an amber banner: "This league is published, so players can see its schedule. Renames show up right away. Removing a team or flight removes its games from the schedule immediately. Other changes take effect when you regenerate, which replaces the schedule."
- **Generate's** confirm text (it already asks when matches exist) adds "Players have already seen this schedule."
- **Deleting a team on a published event needs a new confirm step.** Today the Delete button posts straight away. On published events, Delete opens a Basecoat confirm dialog first: "Delete {team}? This also removes {flight}'s games from the published schedule. Regenerate to rebuild them." Draft events keep today's one-click delete.
- **Removing a flight** in step 3 already asks to confirm. On published events, its text adds that the flight's games disappear from the published schedule.
- **Status stays published after a regenerate,** so players see the new schedule.
- The A13 rule (nothing changes once scores exist) is unchanged.

## 9. Routing changes

- **My Events row link** (`league/views.py:_row_link`): published events go to `event_schedule` if it exists, otherwise to `event_preview`. Until slice 4, that's how she reaches a published league. Drafts with matches already go to `event_preview`.
- **Generate** already redirects to `event_preview` once the URL exists; nothing changes.
- `tests/future_urls.py` needs no change. It already drops any stand-in whose URL name exists for real.

## 10. Constraints

- Django, HTMX 2, Basecoat, and Tailwind via `django-tailwind-cli`. No new JS libraries and no custom JS file.
- Lock the Event row in every write (edits, regenerate, publish), as the wizard does.
- Catch `RestrictedError`, not `ProtectedError` (Match team FKs use RESTRICT).
- On SQLite the row lock is a no-op. That's accepted for now (see carry-forward memory).
- `league/setup_views.py` is already about 600 lines. Put the preview views in a new `league/preview_views.py`, with its templates under `templates/league/preview/`.
- Tests:
  - Engine unit tests for `move_game`.
  - Bridge tests for each edit, refusal, and scored-game guard.
  - View tests through the Django test client, for pick/act, conflict rendering, filters, publish, regenerate, permissions (another org's event → 404; player → refused), and the wizard banners.
  - A screenshot check at 390px and 1280px, per the front-end spec.

## 11. Calls made in this doc (not discussed with the owner)

- Publish redirects to My Events with a toast until P5 exists.
- The fairness rules: what counts as even for each line.
- Faded tiles for games outside the filter. Cancelled, void and withdrawn handling (§5).
- No toast after a successful swap or move.
- Regenerate calls `generate_event` directly.
- Moves can't create a new round.
- Preview views go in a new `league/preview_views.py`.

## 12. Left to the builder

- Exact HTMX targets and partial-template split.
- How the swap is written past the unique constraint.
- Tile markup details within the design-system components.
- Query shape and prefetching for the grid.
