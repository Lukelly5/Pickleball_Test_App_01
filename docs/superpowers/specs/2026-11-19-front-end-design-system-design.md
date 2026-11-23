# Stryde Front End: Design System and App Frame

**Date:** 2026-11-19
**Status:** Approved (2026-11-22)
**Spec it builds on:** `Pickleball League Manager — PRD, ERD & Scheduling Spec.md` (PRD). Sections 2, 3 and 5 define roles, navigation, routes and page layouts. This doc doesn't change any of that. It defines how those pages look and the shared pieces they're built from.

## 1. Intent

Stryde is the owner's own product: a multi-sport league and tournament platform. The first customer is a pickleball league director. She wants to enter teams and players, have the app build the league schedule, and send games out to players. Later, Stryde grows to more clubs and ships as an App Store app.

Two audiences use it:

- **League managers (admins)** set up leagues, generate and adjust schedules, and enter scores. Mostly on a laptop, but score entry happens courtside on a phone. V1 is built mainly for them.
- **Players and spectators** check games, standings and teams, almost always on a phone. They arrive through invite links or the public share link (`/s/<token>/…`).

For this first client, a **phone-friendly website** is enough. There's no App Store app yet. Design choices should still make the later app feel familiar.

## 2. Goals, non-goals, anti-goals

**Goals**
- One consistent Stryde look across all 11 PRD pages, built from a small set of shared components.
- The brand lives in one theme file: colors, fonts, radius. Changing it there changes the whole app.
- Phone-first for P5 (Schedule/Tonight), P8 (Score entry), P11 (My Games) and the share-link pages. Laptop-first for P3 (wizard) and P4 (Schedule Preview), but they still work on a phone.
- The phone experience feels like an app (bottom tab bar), so the future App Store app is a familiar step.

**Non-goals (v1)**
- The App Store app, an API for it, or an installable PWA.
- Brackets. The PRD makes playoff brackets Phase 2–3. The bracket inspiration informs the look of rounds and matchups only.
- A marketing or landing page with a hero photo. The inspiration heroes (Web 02, Padel Club) are not v1 pages.
- Dark mode.
- Self-signup and joining leagues from the app (Phase 2–3 in the PRD).

**Anti-goals (a failure even if it works)**
- Looking like a generic Bootstrap or admin-template site.
- A score entry flow that is fiddly with one thumb at a court.
- Any page that scrolls sideways on a phone. Wide content like the P4 grid scrolls inside its own box.
- Text that is unreadable outdoors in sun because of low contrast.

## 3. Constraints

- Django 6.1 templates, Python 3.13, run through `.venv` (see the project memory). No separate JavaScript front end.
- `TEMPLATES.DIRS` is already `BASE_DIR / "templates"`, and that folder doesn't exist yet.
- No Node.js. CSS is built with the standalone Tailwind binary via `django-tailwind-cli`.
- Every page has the four PRD states: loading (skeleton), empty, error, success (PRD §5).
- Brand assets: `design_ideas/Stryde_Brand_Package.png` (colors, fonts, logo, two UI examples). `design_ideas/` is reference material and is git-ignored. Logo files used by the app must be committed under `static/`.
- Deferred requirements in the project memory (row locking on score save, the "no edits once scores exist" guard, `game_minutes=None` → 15, catching `RestrictedError`) belong to the page slices that touch them, not to this design.

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (picked)** | **Basecoat UI + Tailwind v4 (via `django-tailwind-cli`) + HTMX** | shadcn look as plain HTML classes; brand in one theme file; one extra dev command; long class lists in templates. Tailwind styling carries over to common React Native tools for the future app. |
| B | Handwritten CSS with Stryde CSS variables + HTMX | No build step, full control. Every widget (modal, tabs, dropdown, tables, toasts) built and maintained by hand; slower to get to working pages. |
| C | Bootstrap 5 + crispy forms | Fastest forms, no build. Generic look; time saved goes into overriding it to look like Stryde. |

The owner picked **A**. On 2026-11-19, Basecoat (MIT, ~4.5k stars, Tailwind v4) and `django-tailwind-cli` 4.8.3 (released 2026-11-18, supports Django 6.1, Tailwind 4.x) were both active. Franken UI is the fallback if Basecoat stalls.

## 5. Decisions made with the owner

1. **Visual direction: "Court Light"** (chosen over "Folder Tabs" and a dark "Night Session"). Off-white page, white rounded cards with a soft shadow, Midnight Indigo text, Cobalt for navigation and the selected state, Coral for the main action, Teal for winners and progress.
2. **Phone navigation: bottom tab bar** (chosen over a top bar with a ☰ menu).
   - Player: **My Games · Standings · Account**
   - Admin: **Events · Tonight · Players · More** (More holds Admins, Account, Log out)
   - Admin who also plays (email matches a player, PRD §2): **Events · Tonight · My Games · More**, with Players moved into More. Lands on Events after login. Its laptop top bar is My Events · My Games · Players · Admins · account menu.
   - **Tonight tab (admin):** opens the Tonight view (P5) of the published event with games today. If several events have games today, it shows a short "pick an event" list. If none do, it shows "No games tonight" with the next game night and a link to it. "Today" uses the project time zone (`America/Chicago`).
   - **Standings tab (player):** if the player is on teams in one published event, it opens that event's standings (P6). If they're in several, it shows a short list of their events first. If none: "You're not on any teams yet."
   - These two pages aren't in the PRD. They're thin pickers that route into P5 and P6, built in the slices that build P5 (Tonight) and P6 (Standings). Until then, the tabs are hidden.
   - On laptop widths, both use the PRD top bar (admin: My Events · Players · Admins · account menu; player: My Games · account menu).
   - Share-link visitors: logo and event only. No app navigation (no top bar, no tab bar) and no edit buttons. The event's own underline tabs (Schedule · Standings · Teams, no Settings) count as page content and stay, so visitors can move between the three share-link pages. *My call.* Logged-in players opening an event page keep their bottom tab bar.
3. **Key screens approved as mocked** (P4 Schedule Preview on laptop, P8 Score entry on phone). See §7.
4. **Division colors kept:** every match shows a colored bar for its division. **Intermediate = Cobalt, Advanced = Teal, Beginner = Coral.** Levels are a fixed choice list in `Division.Level`, so the mapping is a simple lookup.

Mockups from the session are saved in `.superpowers/brainstorm/969-1795071773/content/` (`visual-direction.html`, `phone-nav.html`, `key-screens.html`). They're git-ignored, for reference while building.

## 6. The design system

### 6.1 Theme tokens (one file: the Tailwind source CSS)

| Token | Value | Use |
|---|---|---|
| `--color-ink` (Midnight Indigo) | `#0B1A4A` | Body text, headings, dark surfaces |
| `--color-brand` (Cobalt Blue) | `#0B3DCC` | Links, nav active state, selected items, secondary buttons, Intermediate |
| `--color-progress` (Vibrant Teal) | `#14E2B8` | Winning game/score highlight, success, Published status, Advanced |
| `--color-action` (Coral Orange) | `#FF7A3D` | Primary action button (one per screen), Beginner |
| `--color-surface` (Off-White) | `#F6F8FC` | Page background |
| `--color-card` | `#FFFFFF` | Cards, top bar, tab bar |
| `--color-border` | `#E3E8F2` | Card and input borders |
| `--color-warn` / `--color-warn-bg` | `#8A5A00` / `#FFF4E0` | Draft status, fairness warnings (amber) |
| `--color-danger` | `#E5484D` | Swap conflicts, destructive actions, form errors |
| Radius | cards 12–14px, inputs 8–10px, buttons and tabs fully rounded (pill) | |
| Shadow | `0 1px 3px rgb(11 26 74 / .08)` on cards | |

These map onto Basecoat's theme variables (`--primary`, `--background`, `--card`, `--border`, `--destructive`, …). The builder wires the mapping. Templates use the Stryde names or Basecoat's semantic classes, never raw hex values.

**Contrast rule (my call, from checking the brand colors):** white text on Coral is about 2.6:1 and white text on Teal is lower still. Both fail WCAG AA and are hard to read in sun. So **Coral and Teal fills always carry Midnight Indigo text** (about 6.4:1 on Coral). Cobalt with white text (about 8:1) is fine. Teal and Coral are never used as text color on white.

### 6.2 Type

- **Montserrat** 700/800 for page titles, card titles, the wordmark and big numbers (scores, standings ranks).
- **Inter** 400/500/600 for everything else.
- Self-host both under `static/fonts/` (both use the SIL Open Font License) so the app makes no Google request. *My call.*
- Small uppercase labels with letter-spacing (`ROUND 1 · COURT 2 · INT MIXED`) for match metadata, from the brand sheet's match card.

### 6.3 Icons and logo

- **Icons:** Lucide (the set shadcn and Basecoat use), inlined as SVG. *My call.*
- **Logo:** S monogram for the favicon, the phone header and the share-link header. Monogram + "Stryde" wordmark in the laptop top bar. Needs real logo files (see §9).
- **Product name in the UI:** "Stryde". This replaces the PRD wireframes' "Pickleball Manager" and the admin site header.

### 6.4 Layout frame

Three base templates:

- `templates/base.html`: HTML head, fonts, compiled CSS, HTMX, Basecoat JS, Django messages as toasts.
- `templates/base_app.html` (logged in): laptop top bar plus phone bottom tab bar, chosen by role (admin / player / both, per PRD §2). The breakpoint is Tailwind `md` (768px): below it, tab bar; at or above, top bar.
- `templates/base_public.html` (share link and auth pages): logo only.

Page content sits in a max-width container (about 1200px) with 16px phone gutters. On phones, page titles are 20–22px Montserrat 800, with the event's meta line under them in muted text.

### 6.5 Shared components

Built as Django template partials in `templates/components/` (`{% include "components/x.html" with … only %}`). *My call:* plain includes first. `django-cotton` is added only if the includes get awkward. **Build each component when the first page needs it**, not all up front.

| Component | Look | First used by |
|---|---|---|
| Button | Pill. Primary = Coral fill, Indigo text. Secondary = Cobalt fill, white text. Outline = white with border. Ghost = text only. Destructive = red. | Auth, P2 |
| Status badge | Small pill. Draft = amber, Published = teal fill / indigo text, Completed = grey. Account: Not invited / Invited / Active. Withdrawn = grey. | P2, P7, P9 |
| Card | White, 12–14px radius, soft shadow, 12–16px padding | everywhere |
| Data table | Clean rows, muted header, row hover; turns into stacked cards below `md` | P2, P6, P9 |
| Match tile | Small card: division-colored bar on each team, uppercase meta line (flight), two team names. States: selected (Cobalt outline + tint), conflict (red outline + message on the tile), open court (dashed outline, "Open court"). | P4 |
| Match card | Larger card: meta line (round · court · flight), two team rows with division bar, game-by-game score chips. The winning game chip is a teal fill. Unscored: "Enter score" button. | P5 Tonight, P11 |
| Facts strip | Light-blue band with 3 labelled cells (Round · Court · Flight), from the Padel Club inspiration | P11, P5 on phone |
| Tabs (underline) | Event page tabs Schedule · Standings · Teams · Settings. Active = Cobalt with underline. | P5–P7 |
| Tabs (pill/segmented) | Week switcher. Active = Cobalt fill. | P4, P5 |
| Select | Division / Flight dropdowns, Basecoat select | P4–P7 |
| Modal / sheet | Centered dialog on laptop, full-screen sheet on phone. Header with context, sticky footer with the primary button. | P8 |
| Score input | 54×44 boxes, large bold numbers, `inputmode="numeric"`. The winning game turns teal. Focus = Cobalt ring. Live result line ("Dinkers win 2–1"). | P8 |
| Wizard stepper | Numbered steps 1–5 with labels, done / current / upcoming states. Back / Next footer. | P3 |
| Fairness panel | Card of short stat lines, ✓ when even. Amber chip for uneven or long sits. | P4 |
| Toast | Django messages, bottom on phone, top-right on laptop | everywhere |
| Empty state | Lucide icon, one line of PRD copy, primary button when there's an action | all pages |
| Skeleton | Grey rounded bars matching the layout (for HTMX loads) | all pages |
| Error state | PRD copy: "Something went wrong loading this page. Refresh to try again." | all pages |
| Form field | Label above, 10px-radius input, help text muted, error text red under the field | Auth, P3 |

### 6.6 Interaction

- **HTMX** for the in-place updates the PRD calls for: swaps on P4, saving a score from P8 and updating the match card, and wizard steps saving drafts. Without JavaScript, a plain full-page form post still works for scores and wizard steps (*my call*, cheap with Django forms).
- **Basecoat JS** for dialog, dropdown, tabs and toast behavior.
- **Pinned versions** of HTMX and Basecoat, committed under `static/vendor/` rather than loaded from a CDN, so the app works offline in class demos. *My call.*

## 7. How key pages look (reference for the slices)

These follow the PRD page specs and the approved mockups.

**P4 Schedule Preview (laptop)**
```
[S Stryde]  My Events  Players  Admins                          (●)
Spring Tuesday League  [DRAFT · not visible to players]   [↻ Regenerate] [Publish]
( Week 1 | Week 2 | Week 3 | Week 4 )        [Division: All ▾] [Flight: All ▾]
            Court 1         Court 2          Court 3         Court 4
Round 1     ▌Dinkers        ▌Lobsters        ▌Volley Llamas  ▌Lob City
6:30        ▌Smashers       ▌Kitchen Kings   ▌Net Gains      ▌Drop Shots
Round 2     ...             [✕ Smashers already plays this round]   ┆Open court┆
┌ Fairness · Week 1 ─────────────────────────────────────────────┐
│ Games per team: 2 each ✓   Pairs meeting twice: 0 ✓   Longest sit: [Big Dill · 2 rounds] │
└────────────────────────────────────────────────────────────────┘
```
On a phone, the grid scrolls sideways inside its card, and the round labels stay pinned.

**P8 Score entry (phone, full-screen sheet)**
```
Cancel                       Wk 2 · R1 · Court 1
Enter score
Best of 3 · games to 11 · win by 2
            ▌Dinkers   ▌Smashers
Game 1      [11]✓      [ 7]
Game 2      [ 9]       [11]✓
Game 3      [11]       [ – ]
[ Dinkers win 2–1 ]          (teal band)
Mark forfeit
[          Save score          ]   (Coral, Indigo text)
```

**P11 My Games / P5 Tonight (phone):** stacked match cards with the facts strip (Round · time / Court / Flight), the player's own team marked, and the bottom tab bar.

## 8. Build order

Each slice gets its own plan, in the PRD's order:

1. **Frame + auth + My Events:** tooling (`django-tailwind-cli`, Basecoat, HTMX, fonts, logo), theme tokens, the three base templates, the components P1/P2 need, login / invite / password reset, Admin vs Player permissions, P2 with its empty state.
2. P3 wizard (league)
3. P4 Schedule Preview
4. P5 Schedule + Tonight + share link
5. P8 Score entry
6. P6 Standings, P7 Teams
7. P9 Players, P10 Admins, P11 My Games
8. Tournament wizard with fit check

## 9. Open items

- **Logo files:** the owner is adding the monogram and wordmark as separate files to `design_ideas/`. Slice 1 copies them into `static/brand/`. If they haven't arrived when slice 1 starts, use a text placeholder ("S" / "Stryde" in Montserrat 800 italic, Cobalt) and swap later. Never cut artwork out of the brand sheet.

## 10. Left to the builder

- Exact Basecoat style pack and how its variables map to the Stryde tokens.
- Tailwind source file layout and the dev and build commands (`tailwind runserver` vs `tailwind build`).
- Spacing scale details, icon picks per empty state, and skeleton shapes.
- Template tests (render each base and component with the Django test client) and a screenshot check at 390px and 1280px widths for each page slice.
