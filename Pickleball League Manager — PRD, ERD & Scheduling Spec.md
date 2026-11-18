# Pickleball League Manager — PRD, ERD & Scheduling Spec

Nov 17, 2026 · @Luke

## 1. Overview

A Django web app that lets the Director of Pickleball at Waco Regional set teams, weeks, games per week and courts herself, then generates a fair schedule she can tweak before publishing. It replaces Swish, which caps schedules (e.g., 12 games when she needs 16) and gives her no control.

**Problem. **Swish does not allow for optimal customization.

**Solution.** She enters the four controllable inputs: teams, weeks, games per week (can differ week to week) and courts. The scheduler builds a balanced schedule, she previews it, swaps anything she doesn't like and publishes. Players log in to see schedules and standings and, when she allows it, enter their own scores.

**North star.** Create a league → see a correct schedule in seconds → swap a game or two → publish. It should feel instant and obviously fair: every team has a near-equal number of games and nobody is on two courts at once.

**Scope by phase**

| Phase | What ships | Notes |
| --- | --- | --- |
| 1 (class v1) | Leagues and tournaments with fixed 2-player teams; scheduler with preview/swap/publish; admin + player accounts; customizable scoring; standings; Tonight view | Desktop-first, works on a phone |
| 2 | Scramble (rotating partners, individual standings); playoff brackets; player self-signup | Data model is ready for Scramble |
| 3 | AI chatbot that fills the setup form from plain English; installable mobile app; notifications | Chatbot calls the same scheduler |

**Out of scope for v1:** game start times (she sets arrival time herself), payments, court reservations, notifications, Scramble, brackets.

## 2. User types and permissions

Three roles: Admins run everything, Players see everything and score their own matches when allowed, and Spectators view a public link without logging in.

| Action | Admin | Player (logged in) | Spectator (public link) |
| --- | --- | --- | --- |
| View schedule, standings, teams | Yes | Yes | Yes |
| Create / edit leagues and tournaments | Yes | No | No |
| Generate, swap and publish schedules | Yes | No | No |
| Enter or edit any score | Yes | No | No |
| Enter a score for own match | Yes | Only when score entry is on for that event | No |
| Add teams and players, send invites | Yes | No | No |
| Mark a team withdrawn (forfeits) | Yes | No | No |
| Add / remove admins | Yes | No | No |

- **Admin accounts:** the director creates the first admin at setup; any admin can add or remove other admins. The last admin can't be removed.
- **Player accounts:** an admin adds a player with name and email; the player gets an invite link and sets a password. Players who never claim the account still appear on teams and schedules.
- **Spectators:** each published event has a read-only share link. No login.
- *Assumption:* one facility (Waco Regional) in v1, but every record hangs off an Organization so more facilities can be added later.

## 3. Information architecture and navigation

An event (league or tournament) holds divisions by level, each division holds flights by format, and each flight is a self-contained competition with its own teams, schedule and standings.

&#91;embedded content: Event hierarchy · event, division, flight, and what each flight holds\]

The scheduler works per flight for who-plays-whom, but packs all flights onto the same courts on game night.

**Navigation**

- **Top bar (admin):** My Events · Players · Admins · account menu. **Top bar (player):** My Games · account menu.
- **Event page:** Division and Flight dropdowns at the top, then tabs Schedule | Standings | Teams | Settings (Settings is admin only).
- **Tonight shortcut:** a button on the Schedule tab that jumps to the current week across *all* divisions and flights, grouped by round then court. It is the default view on a game night.
- **Spectators** get the event page through a share link, with no top bar and no edit buttons.

## 4. Core user flows

Six flows cover v1; Flow A is the north star and gets built first.

### Flow A — Create a league and publish its schedule (north star)

**Entry:** My Events → "+ Create".

1. **Basics:** name, type = League, start date, number of weeks, number of courts.
2. **Scoring:** match format (1 game / best of 3 / best of 5), points to win (11 / 15 / 21), win by 2 (on/off), player score entry (on/off).
3. **Divisions and flights:** tick a grid of Level × Format (e.g., Intermediate × Mixed). Each ticked cell becomes a flight.
4. **Teams:** per flight, add teams (name + 2 players). Pick an existing player or add a new one by name and email.
5. **Games plan:** per flight, choose "each team plays every other team: once / twice / custom". Once or twice fills the per-week games grid automatically; custom lets her type games per week (Week 1: 5, Week 2: 6…). A live summary shows the result: "16 games · 8 per team · every pair meets 2–3 times".
6. **Generate:** the scheduler builds a draft and opens Schedule Preview.
7. **Preview and swap:** she clicks two games (or two teams in a game) to swap them. Conflicts show inline before she confirms.
8. **Publish:** schedule becomes visible to players and spectators; invites go out to unclaimed players.

**Success:** league page opens on the Schedule tab with a banner "Schedule published · 16 games over 4 weeks".

**Errors:**

- Flight with fewer than 2 teams: "Add at least 2 teams to Intermediate Mixed before generating."
- Games per week can't be played: "Week 2 asks for 6 games but 4 teams can play at most 2 at once per round on 2 courts. That's fine — it will take 3 rounds." (warning, not a block)
- Uneven week: "Week 2: 2 teams play twice, 8 play once." (warning)
- Swap creates a clash: "Team Dinkers would play on Court 1 and Court 3 in Round 2. Swap anyway?" (blocked for team clashes; player clashes across flights are blocked too)

**Alternative:** "Regenerate" throws away swaps and rebuilds from the inputs (confirm first: "Regenerating discards your 3 swaps.").

### Flow B — Game night: enter scores

**Entry:** league page → Schedule tab → "Tonight".

1. Tonight lists every flight's games for the current week, grouped by round, then court.
2. Admin (or a player on that match, if score entry is on) taps "Enter score".
3. Score form shows one row per game in the match format (1, 3 or 5 rows), validated against points-to-win and win-by-2.
4. Save → the game card shows the result and standings update.

**Errors:** "Games to 11 must be won by 2 — 11–10 isn't a final score." · "A best-of-3 match ends when one team wins 2 games." · Player not on the match: the button doesn't appear.

**Alternative:** "Mark forfeit" on a match → choose which team forfeited → the other team gets the win.

### Flow C — Create a tournament (with fit check)

Same wizard as Flow A with type = Tournament. Weeks are replaced by a date, a time window (e.g., 60 min) and an estimated game length (default 15 min, *assumption*). Games plan is fixed to round robin once.

**Fit check (live in step 5):**

- Fits: "28 games · 7 rounds on 4 courts · about 1h 45m. Fits your 2-hour window."
- Doesn't fit: "28 games need 7 rounds on 4 courts (\~1h 45m). Your 60-minute window fits 4 rounds. Add courts, extend the window, or cap games per team."

Cap games per team = the scheduler stops each team at N games, keeping matchups as varied as possible.

### Flow D — Player claims an account

1. Admin adds the player (name + email) → invite email goes out when the event is published (or via "Send invite").
2. Player opens link → sets password → lands on "My Games": their teams, next match, standings.

**Errors:** "This invite link has expired. Ask your league admin to resend it." · "That email already has an account — log in instead."

### Flow E — Manage admins

Admins page → "Add admin" (email) → they get an invite → appear in the list. "Remove" asks to confirm. **Error:** "You can't remove the last admin."

### Flow F — A team drops out

Teams tab → team → "Withdraw team" → confirm: "Mark Team Dinkers withdrawn? Their 6 remaining games become forfeit wins for their opponents." Played games stay as they are.

## 5. Page specs

Eleven pages. Every page has four states: loading (skeleton rows), empty, error ("Something went wrong loading this page. Refresh to try again."), and success.

| # | Page | Route | Access |
| --- | --- | --- | --- |
| P1 | Log in / accept invite | `/login`, `/invite/<token>` | Everyone |
| P2 | My Events (admin home) | `/events` | Admin |
| P3 | Create / edit event wizard | `/events/new`, `/events/<id>/setup` | Admin |
| P4 | Schedule Preview (draft) | `/events/<id>/preview` | Admin |
| P5 | Event page — Schedule tab + Tonight | `/events/<id>/schedule` | All (spectators via share link) |
| P6 | Event page — Standings tab | `/events/<id>/standings` | All |
| P7 | Event page — Teams tab | `/events/<id>/teams` | All (edit: admin) |
| P8 | Score entry (modal) | over P5 | Admin; player on match if enabled |
| P9 | Players directory | `/players` | Admin |
| P10 | Admins | `/admins` | Admin |
| P11 | My Games (player home) | `/me` | Player |

### P2 — My Events

Table of events, newest first. Columns: name, type, dates, flights, status (Draft / Published / Completed). Row click → P5 (or P4 if draft).

```
[Pickleball Manager]  My Events | Players | Admins        Luke ▾
---------------------------------------------------------------
My Events                                          [+ Create]
Name                     Type        Dates          Status
Spring Tuesday League    League      Mar 3–Mar 24   Published
March Madness Shootout   Tournament  Mar 14         Draft
```

**Empty:** "No events yet. Create your first league or tournament." + Create button.

### P3 — Create event wizard

Five steps with a progress bar; Back/Next; saves as a draft after every step so nothing is lost.

```
Create league   (1 Basics)—(2 Scoring)—(3 Flights)—(4 Teams)—(5 Games plan)
---------------------------------------------------------------
5. Games plan — Intermediate Men's (4 teams)
Each team plays every other team:  ( ) once  ( ) twice  (•) custom
        Wk1  Wk2  Wk3  Wk4      Total
Games   [4]  [4]  [4]  [4]      16
ℹ 16 games · 8 per team · every pair meets 2–3 times
                                   [Back]  [Generate schedule]
```

- Step 3 is a checkbox grid: rows Beginner / Intermediate / Advanced, columns Men's / Women's / Mixed.
- Step 4 has a flight switcher on the left and a team list on the right; "+ Add team" opens an inline row: team name, Player 1, Player 2 (type-ahead from the players directory, or "+ New player").
- Tournament mode swaps weeks for date + window + game length and shows the fit check in step 5.

### P4 — Schedule Preview (draft)

The north-star screen. One week at a time (week tabs across the top); a grid of rounds (rows) × courts (columns). Division and Flight dropdowns filter it; "All flights" shows everything on the courts that night.

```
DRAFT — not visible to players          [Regenerate] [Publish]
Week: [1] 2 3 4        Division [All ▾]  Flight [All ▾]
---------------------------------------------------------------
          Court 1               Court 2
Round 1   Dinkers v Smashers    Lobsters v Kitchen Kings
Round 2   Dinkers v Lobsters    Smashers v Kitchen Kings
---------------------------------------------------------------
Per team this week: Dinkers 2 · Smashers 2 · Lobsters 2 · KK 2
```

- **Swap:** click a game (highlighted), click another game → they trade slots. Click a team name inside a game, then another team name → the teams trade. A conflict shows a red outline and the message from Flow A before it saves.
- **Fairness panel** under the grid: games per team (this week and total), times each pair meets. Anything uneven shows in amber.
- **Edge:** if she edits inputs in P3 after swapping, preview warns "Inputs changed — regenerate to apply them."

### P5 — Event page: Schedule tab and Tonight

Top: event name, Division and Flight dropdowns, tabs Schedule | Standings | Teams | Settings (admin only). Schedule lists weeks; each week expands to rounds and courts. "Tonight" (button, default on a game night) jumps to the current week across all flights, grouped by round then court.

```
Spring Tuesday League      Division [Intermediate ▾] Flight [Men's ▾]
Schedule | Standings | Teams | Settings                 [Tonight]
---------------------------------------------------------------
TONIGHT — Week 2 · all flights
Round 1  Court 1  Int Men's   Dinkers 11–7 Smashers        ✓
         Court 2  Int Men's   Lobsters v Kitchen Kings [Enter score]
         Court 3  Adv Mixed   Volley Llamas v Net Gains [Enter score]
```

**Empty (no schedule yet):** "The schedule hasn't been published yet." Spectators see the same page without buttons.

### P6 — Standings tab

One table per flight, sorted by wins, then point differential, then head-to-head (*assumption*).

```
Intermediate Men's — after Week 2
#  Team            GP  W  L  PF  PA  Diff
1  Dinkers          4  3  1  41  30  +11
2  Smashers         4  2  2  38  37   +1
```

Forfeit wins count in W but not in PF/PA/Diff. A small "F" marks forfeit results in the team's game list. **Empty:** "Standings appear after the first score is entered."

### P7 — Teams tab

List of teams in the selected flight: name, two players (with "invited" / "active" badge for admins), record. Admin actions: edit team, withdraw team (Flow F). Withdrawn teams show greyed with "Withdrawn".

### P8 — Score entry (modal)

```
Dinkers vs Smashers · Week 2 · Round 1 · Court 1
Best of 3 · games to 11 · win by 2
         Dinkers   Smashers
Game 1   [11]      [ 7]
Game 2   [ 9]      [11]
Game 3   [11]      [ 5]
[Mark forfeit]                         [Cancel] [Save]
```

Game 3 appears only when games are 1–1. Save is disabled until the result is valid. Edits after saving keep a "last edited by" line.

### P9 — Players directory

Searchable table: name, email, teams, account status (Not invited / Invited / Active). Actions: add player, send/resend invite, edit. **Empty:** "No players yet. Players are added when you create teams, or here."

### P10 — Admins

List of admins with "Remove"; "+ Add admin" by email. Last admin's Remove is disabled with a tooltip.

### P11 — My Games (player home)

Cards: "Next up" (event, week, round, court, opponent), my teams with record, link to each event's standings. **Empty:** "You're not on any teams yet."

## 6. Scheduling logic spec

The scheduler is plain, repeatable logic (no AI): the same inputs always produce the same schedule. It works in two passes — first decide **who plays whom** each week, then place those games into **rounds and courts** for the night.

### Inputs

- **Per event:** number of courts; weeks (league) or time window + game length (tournament).
- **Per flight:** its teams; games per week (a number for each week). "Once" / "twice" round robin just pre-fills games per week so the total equals once or twice through every pairing, spread as evenly as possible across weeks.

### Rules

| Type | Rule |
| --- | --- |
| Hard | A team plays at most one game per round. |
| Hard | A player plays at most one game per round, across all flights (one person can be on a Men's and a Mixed team). |
| Hard | At most one game per court per round. |
| Hard | Teams only play teams in their own flight. |
| Soft | Games per team stay within 1 of each other at all times (each week and in total). |
| Soft | Every pair meets k times before any pair meets k+1 times. |
| Soft | Byes (odd team counts) rotate so nobody sits out twice before everyone has sat out once. |
| Soft | Flights sharing courts are interleaved so one flight doesn't finish an hour after another. |

### Pass 1 — Who plays whom

1. Build one full round robin per flight using the standard **circle method**: fix one team, rotate the rest one seat each round. With N teams this gives N−1 "rotations" where every team plays exactly once (odd N: add a placeholder "BYE" team, giving N rotations with one team resting each).
2. Put those games in one long list, rotation by rotation, and let it repeat (second time through = the rematches).
3. For each week, take the next *g* games off the list, where *g* is that week's games-per-week number. Carry the position over to the next week.

Because the list goes rotation by rotation, this automatically keeps games per team within 1 of each other and spreads rematches evenly. No search or optimisation needed.

### Pass 2 — Rounds and courts for the night

1. Gather every game that night from every flight.
2. Fill Round 1, Court 1 onward: put a game in the earliest round where it has a free court and none of its 4 players is already playing. Take games from each flight in turn so flights stay interleaved.
3. Repeat until every game is placed. The number of rounds used is the length of the night.
4. **Tournament fit check:** rounds needed × game length vs the time window. If it doesn't fit, show the Flow C message and offer "cap games per team".

### Worked test cases (acceptance tests)

Each case is a unit test: given these inputs, the generated schedule must match the expected result.

**T1 — Her Swish example: 4 teams, 4 weeks, 4 games a week, 2 courts.** Teams A, B, C, D. Rotations: R1 = AB, CD · R2 = AC, BD · R3 = AD, BC.

| Week | Games taken | Rounds that night |
| --- | --- | --- |
| 1 | R1 + R2: AB, CD, AC, BD | 2 rounds × 2 courts |
| 2 | R3 + R1: AD, BC, AB, CD | 2 rounds × 2 courts |
| 3 | R2 + R3: AC, BD, AD, BC | 2 rounds × 2 courts |
| 4 | R1 + R2: AB, CD, AC, BD | 2 rounds × 2 courts |

Expected: 16 games; every team plays 2 a night and 8 total; AB, CD, AC, BD meet 3 times, AD and BC meet 2 times. (Swish stops at 12.)

**T2 — Uneven week: 10 teams, Week 1 = 5 games, Week 2 = 6 games, 5 courts.** Week 1 = rotation 1, everyone plays once, 1 round. Week 2 = rotation 2 (5 games) + first game of rotation 3 → 2 rounds (5 games, then 1). Expected warning: "Week 2: 2 teams play twice, 8 play once."

**T3 — Tournament that doesn't fit: 8 teams, round robin once, 4 courts, 15-min games, 60-min window.** 28 games; at most 4 games per round (8 teams) → 7 rounds → 105 min. Expected: fit-check failure message; capping at 4 games per team → 16 games → 4 rounds → fits.

**T4 — Odd teams: 5 teams, round robin once, 2 courts.** 10 games over 5 rotations; each rotation has 2 games and 1 bye. Expected: every team gets exactly one bye; 5 rounds.

**T5 — Player in two flights.** Pat is on an Intermediate Men's team and an Intermediate Mixed team playing the same night. Expected: Pat's two games are never in the same round, even if that adds a round.

**T6 — Swap conflict.** In T1 Week 1, swapping AB (Round 1) with BD (Round 2) puts D in two games in Round 1 and A in two games in Round 2 → blocked with the Flow A message. (For all tests, assert these properties rather than exact pairings, since the circle method may order rotations differently.)

## 7. Data model (ERD)

Twelve tables. The scheduler's output is a set of Match rows; standings are calculated from Match and GameScore, never stored, so they can't drift out of sync with the scores.

&#91;embedded content: ERD · 12 tables for v1\]

**How data flows**

1. Setup writes Event → Division → Flight → Team (+ Player and TeamMember) and one Week per league week.
2. Generate creates Match rows with `status = scheduled` while the Event is `draft`. Swaps just edit `round_no`, `court_no` or the team links on those rows.
3. Publish flips Event to `published`; players and spectators can now see the Matches.
4. Score entry adds GameScore rows, sets `winner` and `status = final` on the Match. A forfeit sets `forfeited_by` and `winner` with no GameScores.
5. Standings = a query over final Matches per Flight: wins, then point differential (forfeits excluded from points).

**Design choices**

- `games_per_week` is a list on Flight (e.g., `[5, 6, 5, 5]`) rather than its own table. It's simpler, and the custom grid in the wizard edits it directly.
- Player and User are separate. An admin can add players who never log in; `user` fills in when they accept the invite. This is also what makes self-signup (Phase 2) easy.
- **Scramble path (Phase 2):** add a `MatchSide` table (match, side A/B) with a `MatchSidePlayer` link, and make the team links on Match optional. Leagues keep working, and Scramble games list players instead of teams.
- Validation to enforce in code: a team has exactly 2 TeamMembers; both teams in a Match belong to the Match's Flight; no team or player twice in the same week and round.

## 8. Assumptions, risks and build checklist

### Assumptions to confirm with the client

Each was a default chosen during planning; check them if you get the chance to talk to her.

| # | Assumption | Why it matters |
| --- | --- | --- |
| A1 | Rounds have no clock times; she announces the start time herself | Keeps start times out of the data model |
| A2 | Default game length for tournaments is 15 minutes | Drives the fit check |
| A3 | Defaults: 1 game per match, to 11, win by 2 | Pre-fills the scoring step |
| A4 | Final standings tie-break is head-to-head, then team name | Needed when wins and differential tie |
| A5 | Forfeits count as a win but not in points for/against | Stops no-shows from inflating differential |
| A6 | Withdrawn team's remaining games become forfeits; played games stand | Flow F |
| A7 | All flights in an event share the same courts and nights | Pass 2 packs all flights together |
| A8 | Spectators need no login (public share link) | Lowest friction for families and friends |
| A9 | Players may edit their own match score until an admin edits it | Prevents score tug-of-war |

### Risks

- **Scheduler edge cases eat the timeline.** Mitigation: build Pass 1 + tests T1–T4 in week one, before any UI.
- **Swap UI is the hardest screen.** Mitigation: ship click-to-select-then-click-to-swap (no drag and drop) with HTMX partial reloads.
- **Invites need email.** Mitigation: use Django's console email backend for the class demo; real SMTP later.

### Build order and checklist

Suggested stack: Django + Django templates + HTMX for in-place updates (swap, score entry) + a simple CSS framework. No separate front end needed.

- [ ] Models and migrations for the ERD (Section 7); Django admin registered for quick data entry
- [ ] Scheduler module (pure Python, no Django imports) + unit tests T1–T6
- [ ] Auth: login, invite token, set password, Admin vs Player permissions
- [ ] P2 My Events with empty state
- [ ] P3 wizard steps 1–5, saving a draft after each step; tournament variant with fit check
- [ ] P4 Schedule Preview: week tabs, round × court grid, swap with conflict check, fairness panel, Regenerate, Publish
- [ ] P5 Schedule tab + Tonight view, Division/Flight dropdowns, public share link
- [ ] P8 Score entry modal with format validation and forfeit
- [ ] P6 Standings (computed from scores)
- [ ] P7 Teams tab with withdraw
- [ ] P9 Players directory, P10 Admins, P11 My Games
- [ ] Seed script: one league (3 divisions × 2 flights, 4–6 teams each, 4 weeks) and one tournament, so the demo never starts empty

### Phase 2–3 hooks already in the design

Scramble (individual entries in matches), playoff brackets (a match can point to the next match), self-signup (Player already links to a login), AI chatbot setup (fills the same wizard fields, calls the same scheduler).
