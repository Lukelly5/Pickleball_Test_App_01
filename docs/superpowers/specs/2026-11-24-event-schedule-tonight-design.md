# Slice 4: Event page — Schedule tab, Tonight and share link (P5) design

**Status:** approved · 2026-11-24
**Builds on:** PRD §3 (event page, Tonight shortcut, spectators), §5 P5, assumption A8 (spectators need no login). Front-end spec §5.2 (nav, Tonight tab, share-link chrome) and §6.5 (match card, facts strip, underline tabs, segmented tabs). Slice 3 (Schedule Preview, publish).

## 1. Intent

Once a league is published, everyone needs to see it. On a game night the director at the desk, and players courtside, want to know who is on which court in which round. Families and friends want to follow along without making an account. This slice gives a published event its own page: a Schedule tab that shows one week at a time, a **Tonight** view of the current week across every flight, and a public share link.

Success: starting from a draft league (`seed_demo` already publishes the demo league so players have games to see, so the walk-through test puts it back to draft first), an admin publishes, lands on the event page, flips through weeks with the pills, filters by division and flight, opens Tonight, copies the share link, and opens it in a private window on a phone (390 px wide). There she sees the same schedule with only the logo on top and no buttons. A logged-in player reaches the same page from My Games.

## 2. Goals, non-goals, anti-goals

**Goals**
- `/events/<id>/schedule/` (URL name `event_schedule`): the Schedule tab, with week pills, Division and Flight dropdowns, and the Tonight view.
- Event-page tabs Schedule · Standings · Teams · Settings (Settings for admins only). Standings and Teams are "Coming soon" stubs in this slice.
- `/events/<id>/settings/` (admin): the share link with Copy and Reset, and a link to edit the league in the setup wizard.
- `/s/<token>/schedule/` (plus stub `/s/<token>/standings/` and `/s/<token>/teams/`): the public share-link pages.
- `/tonight/` (URL name `tonight`, admin): turns on the hidden Tonight tab in the app nav.
- A share token is created when a league is published.
- Publishing from the Preview now lands on the event page.
- My Games cards link to their event's Schedule tab.

**Non-goals (later slices)**
- Score entry and the "Enter score" button (slice 5, P8). Scores that already exist are shown.
- Standings (P6) and Teams with withdraw (P7) content.
- Round start times. None are stored, so rounds stay "Round 1", "Round 2".
- Splitting `league/setup_views.py`. Still wanted, but it isn't part of this slice (carry-forward memory keeps it).
- Locking the setup wizard for published events. Slice 3 settled this: allowed, with a warning.
- Anything tournament-specific. Tournament matches use the same tables, so the page should show them, but nothing is built or tested for tournaments.

**Anti-goals**
- Leaking a draft. A draft event is never visible to players or through a share link.
- Leaking across organizations. A logged-in user only sees events in their own organization.
- Edit buttons or app navigation on share-link pages.
- A page that scrolls sideways on a phone.

## 3. Approaches considered

**How weeks are laid out (owner picked A)**

| Option | Trade-off | Verdict |
| --- | --- | --- |
| **A. Week pills, one week at a time** (as on the Preview) | Short on a phone; admins already know it from the Preview; matches the design-system spec. Seeing the whole season takes a tap per week. | **Picked** |
| B. Expandable list of every week (PRD wording) | Whole season in one scroll, but long and tap-heavy on a phone. | Rejected |

**How the page is built (owner picked B)**

| Option | Trade-off | Verdict |
| --- | --- | --- |
| A. Reuse the Preview's `build_board` grid | Most reuse, but the board is a laptop round × court grid built around pick-and-swap (tile keys, open courts, click rules). The read-only page would carry all of it, and Tonight's all-flights list would still need its own code. | Rejected |
| **B. A small read-only builder** (`league/schedule_page.py`) | Turns one week into a plain list of rounds and match cards. Tonight uses the same builder with no filter. One set of views serves admins, players and spectators, with a flag for share-link mode. Score entry later adds its button to the match card in one place. | **Picked** |
| C. A separate public app for share links | Duplicates every template for no gain. | Rejected |

## 4. The Schedule tab

```
Spring Tuesday League                          [Tonight]
Schedule | Standings | Teams | Settings
Division [All ▾]  Flight [All ▾]
( Wk1 )(•Wk2•)( Wk3 )( Wk4 )                 Tue Dec 2
───────────────────────────────────────────────
Round 1
  ┌ ROUND 1 · COURT 1 · INT MEN'S ──────────┐
  │ ▌Dinkers        11  9 11                 │
  │ ▌Smashers        7 11  5                 │
  └──────────────────────────────────────────┘
  ┌ ROUND 1 · COURT 2 · INT MEN'S ──────────┐
  │ ▌Lobsters                                │
  │ ▌Kitchen Kings                           │
  └──────────────────────────────────────────┘
Round 2
  ...
Sitting out Round 2: Smashers           (single flight only)
```

- **Header:** the event name and a Published or Completed badge. The **Tonight** button sits at the right (§5).
- **Event tabs:** underline tabs (design-system spec). Settings appears only for admins. On share-link pages the tabs are Schedule · Standings · Teams and point at the `/s/<token>/…` routes.
- **Dropdowns:** Division and Flight, each with "All". Picking a division narrows the Flight list. Kept in `?division=` and `?flight=` with the same values and junk handling as the Preview (reuse or share the reading code from `league/preview.py: parse_state`; the `pick` part doesn't apply).
- **Week pills:** segmented tabs, kept in `?week=`. The selected week's date shows beside the pills when it has one. A cancelled week's pill reads "Wk3 · Cancelled" and the body says "No games this week (cancelled)."
- **Default week** when `?week=` is missing or junk (*my call*), using today's date in `America/Chicago` (`django.utils.timezone.localdate()`):
  1. a week dated today that isn't cancelled → open in **Tonight** mode (§5);
  2. else the first week dated after today;
  3. else the last week (the season is over);
  4. if no week has a date, Week 1.
- **Body:** rounds in order. Each round lists its matches by court as match cards (design-system spec §6.5): a meta line (round · court · flight name), two team rows with the division color bar, and game-by-game score chips when scores exist. The winner's row is bold and each won game's chip is filled teal. A forfeit shows "Forfeit" and the winner, with no chips. Withdrawn teams get a "Withdrawn" badge. Cancelled or void matches show faded with their status.
- **Sit-outs** (*my call*): when a single flight is selected, each round ends with "Sitting out: …" listing that flight's active teams that have no game in the round, if any. With several flights shown it's left out, because the list gets long.
- **Your team** (*my call*, from the design-system spec): for a logged-in player (or admin who plays), their own team's name is marked on each card (e.g. a "You" chip). Not on share-link pages.
- **Empty states:**
  - Week with no games for the filter: "No games for this flight this week."
  - Event with no matches at all (published, then every team deleted in setup): "The schedule hasn't been published yet." Spectators see the same text.
- **Updating in place:** pills, dropdowns and the Tonight button are links/GET forms enhanced with HTMX (`hx-get`, `hx-push-url`) that swap only the page body. Follow the Preview's pattern: return the partial for `HX-Request` but the full page for `HX-Restore-Request`/history restore, and add `Vary: HX-Request`. Without JS everything works as full-page loads.
- **Phone:** cards stack full width; dropdowns sit side by side; pills scroll inside their own row. Nothing scrolls the page sideways at 390 px.

## 5. Tonight

- **Button:** `?view=tonight` on the Schedule tab. It clears the division and flight filters, picks the week dated today, and shows every flight for that week grouped by round, then court. The heading reads "Tonight — Week 2 · all flights".
- **Game night:** when the Schedule tab opens with no `?week=` and a non-cancelled week is dated today, it opens in Tonight mode.
- **Not a game night:** Tonight shows "No games tonight." plus, if one exists, "Next game night: Tue Dec 9 · Week 3" linking to that week. If there's no later dated week, just "No games tonight."
- **Choosing a filter or pill** leaves Tonight mode and shows the normal Schedule view.
- Tonight is built by the same builder as the Schedule body (no filter, all flights), so cards look the same. Sit-outs are not shown (several flights).

## 6. App nav: the Tonight tab (`/tonight/`)

Admin only (front-end spec §5.2). Adding the `tonight` URL name makes the tab appear in the admin nav automatically (`ui/nav.py` hides items whose URL doesn't reverse).

- Exactly one published event in her organization has a non-cancelled week dated today → redirect to that event's Schedule tab with `?view=tonight`.
- Several → a short list: event name and "Week N", each linking to its Tonight view.
- None → "No games tonight." with the next game night across her published events (event name, date, week) and a link, if there is one.
- Drafts and completed events are ignored.

Players keep their current nav (My Games · Standings · Account); they reach event pages from My Games.

## 7. Settings tab (`/events/<id>/settings/`, admin)

```
Share link
Anyone with this link can see the schedule, standings and teams. No login needed.
[ https://…/s/Xk3…/schedule/ ]  [Copy]
[Reset link]   (confirm: "The old link will stop working. Reset?")

Edit league
[Edit setup]  → /events/<id>/setup/ (shows its published warning)
```

- **Copy:** copies the full absolute URL (`request.build_absolute_uri`). Use whatever copy pattern the invite "Copy invite link" button already uses, if one exists; otherwise a few lines of inline JS with the input selectable as a fallback.
- **Reset:** POST, with a confirm step done server-side or with HTMX (not a browser `confirm()` dialog). Sets a new token; the old URL then returns 404. Success toast "New share link created."
- If a published event has no token (events published before this slice, or seed data), the Settings view creates one on first view.

## 8. Who sees what

| Visitor | Published / completed event | Draft event |
| --- | --- | --- |
| Admin of the event's organization | Everything, all four tabs | `/events/<id>/schedule/` redirects to the Preview |
| Logged-in player (or admin) in the organization | Schedule, Standings, Teams; no Settings, no buttons | 404 |
| Logged-in user in another organization | 404 | 404 |
| Anonymous with the event URL | Redirect to log in | Redirect to log in |
| Anyone with a valid share link | Schedule, Standings, Teams in `base_public.html` (logo only, no app nav) | 404 (a draft has no token; if one exists anyway, still 404) |
| Wrong or reset share token | 404 | 404 |

- The event page uses `base_app.html` for logged-in users (keeping the bottom tab bar) and `base_public.html` for share-link visitors, with the event header and tabs as page content in both.
- **Share-link visitors keep Tonight** (*my call*): the Tonight button, automatic Tonight mode on a game night, week pills and dropdowns all work the same. "No buttons" means no edit or admin controls (Settings tab, future Enter score) and no "You" chip.
- Share-link pages send `X-Robots-Tag: noindex` (*my call*) so search engines don't list them.
- `Settings` is `admin_required` plus same organization.

## 9. Share token

- `Event.share_token` already exists (nullable, unique). Create it with `league.models.new_token()` when `schedule_edits.publish` flips the status, inside the same transaction.
- `seed_demo` sets the token on the league it publishes.
- A helper on `Event` (e.g. `ensure_share_token()`) is used by publish, seed and the Settings view; `reset_share_token()` is used by Reset.
- No migration needed. Existing published events without a token get one from the Settings view.

## 10. Other changes

- **Publish:** `event_preview_publish` now redirects to `event_schedule` with the existing success toast (previously My Events).
- **My Events:** `_row_link` already prefers `event_schedule` for non-drafts once the URL exists; no change beyond checking it.
- **My Games:** each team card links to its event's Schedule tab filtered to the team's flight.
- **`seed_demo --tonight`** (owner picked): a new option that shifts the demo league's week dates so Week 2 is today (in `America/Chicago`) and Week 1 was a week earlier, keeping the weekly spacing. Without the flag the seed is unchanged (league dated from 2027-03-02, published). Run it right before a class demo so Tonight has games.
- **PRD checklist:** tick Auth, P2, P3 and P4, which earlier slices built, and P5 when this slice ships.

## 11. Testing

- **Builder** (`league/schedule_page.py`): default-week rules (today, next, last, no dates); filters; rounds and courts in order; sit-outs for one flight only; cancelled week; cancelled/void matches; forfeit and scored cards; withdrawn badge; Tonight with and without a game today and the "next game night" lookup. Freeze "today" by passing a date into the builder rather than patching the clock.
- **Views:** the who-sees-what table in §8, row by row; HTMX partial vs full page and history restore; `Vary` header; share token created on publish; reset makes the old link 404; `/tonight/` with zero, one and several events.
- **End to end** (like slices 2 and 3): seed → publish → event page → pills and filters → Tonight → copy link → share page, plus a 390 px check that nothing scrolls sideways.

## 12. Left to the builder

- Module and template names beyond those given; how to share `parse_state`'s filter reading with the Preview.
- Exact card markup, within the design-system components.
- Whether the Standings/Teams stubs are one shared template.
- The copy-to-clipboard mechanism (§7).
