# Slice 5: Score entry (P8) design

**Status:** approved · 2026-11-25
**Builds on:** these sources:
- PRD §3 Flow B (enter scores), §4 permissions table, §5 P8 mock, §7 data rules 4–5, and assumptions A5, A9, A12 and A13.
- Front-end spec §6.5 (modal/sheet, score input, match card) and §7 (P8 phone mock).
- Slice 4 event page: the match card in `templates/league/event/_card.html`, and `league/schedule_page.py`.
- Carry-forward memory: score save must take the Event row lock.

## 1. Intent

On game night the director, and players when she allows it, enter scores courtside on a phone. They do it from the match cards on the Tonight and Schedule views. The form knows the event's format (1, 3 or 5 games; to 11, 15 or 21; win by 2 or not) and holds players to it. Admins can override the points rules, because a timed game can legitimately end 9–7. A forfeit gives the other team the win.

Saving updates the card in place. The scores are stored the way the Standings slice (P6) will read them.

Success means three walk-throughs work:
- On a phone at 390 px, an admin opens Tonight and taps "Enter score" on a best-of-3 match. She types 11–7 and 9–11, sees Game 3 appear, types 11–5, sees "Dinkers win 2–1", and saves. The card now shows the chips and "Last edited by …".
- A player on the match does the same when player score entry is on. They are blocked by a "11–10 isn't a final score" message, and can't change the score after the admin has edited it.
- An admin clears a mistaken forfeit, and the match is unscored again.

## 2. Goals, non-goals, anti-goals

**Goals**
- "Enter score" and "Edit score" buttons on match cards (logged-in event pages only). The form is a sheet: full-screen on a phone, a centered dialog on a laptop.
- Live checking as games are entered: Game 3 (or Games 4 and 5) appears only when needed, a result line shows, and rule messages appear.
- Strict rules for players. For admins, a warning with "Save anyway".
- Mark forfeit and Clear score for admins.
- "Last edited by …" on scored cards. Players are locked out once an admin has saved, cleared or forfeited the match (A9).
- Every write takes the Event row lock (closes the A13 race noted in the carry-forward memory).

**Non-goals (later slices)**
- Standings (P6). The data written here is what P6 will read, but no standings page is built.
- Withdrawing a team and its automatic forfeits (P7).
- Score entry from My Games (P11).
- Tournaments. Matches share tables, so nothing should break for them, but nothing is built or tested for them.
- Notifications, score history or audit log beyond "last edited by".

**Anti-goals**
- A score form that is fiddly with one thumb: small boxes, a non-numeric keyboard, or the page jumping while typing.
- A player changing a score an admin has set, or scoring a match they aren't on.
- Two copies of the scoring rules (JS and Python) that can disagree.
- Any score control on share-link pages.

## 3. Approaches considered

**What "Save anyway" can save when no team leads** (owner picked A)

| Option | Trade-off | Verdict |
| --- | --- | --- |
| **A. A winner is always required** | "Save anyway" only waives the points rules (9–7 is fine), but one team must lead on games won. Every saved match has a winner, so standings stay simple. | **Picked** |
| B. Save without a winner | Honest for an unfinished night, but the card and standings need an "unfinished" state. | Rejected |
| C. Admin picks the winner when the games don't decide it | Flexible, but the recorded games and the winner can disagree. | Rejected |

**How the form is built** (owner picked A)

| Option | Trade-off | Verdict |
| --- | --- | --- |
| **A. Sheet kept up to date by the server (HTMX)** | One copy of the rules in Python. The live check and the save can't disagree. Matches the P8 mock. Each box change is a small round trip. Without JS it falls back to a plain page. | **Picked** |
| B. Plain score page | Simplest and sturdy on bad connections. Loses the live result line, the sheet and the in-place card update. | Rejected (kept as A's no-JS fallback) |
| C. Rules checked in the browser | Snappiest, but the rules exist twice and it breaks the project's no-custom-JS rule. | Rejected |

## 4. Who can score what

| Visitor | Can enter or edit a score? |
| --- | --- |
| Admin of the event's organization | Yes, on any match of a published or completed event, any week. |
| Player on one of the match's two teams | Only if all of these hold: the event has `player_score_entry` on; the event is published; the week's date is today or earlier, or the week has no date (*my call*); and no admin has saved, cleared or forfeited the match (A9). |
| Any other logged-in user | No (no button; the URLs return 404 for other orgs, 403 for same-org non-members). |
| Share-link visitor | No button, no URLs. |

"Player on the match" means `accounts.roles.player_for(user)` is a member of `team_a` or `team_b`. An admin who also plays counts as an admin.

**No button, and the URLs refuse** (*my call*) for these cases:
- a cancelled week;
- a match with status cancelled or void;
- a match where either team is withdrawn;
- a draft event.

**A9 test:** the match is admin-locked when `last_edited_by` is set and `last_edited_by.is_admin`. No new field (*my call*). If that user is later deleted, `last_edited_by` becomes null and players could edit again, which is acceptable.

## 5. The score rules

These rules live in one pure-Python module with no HTTP code. The live check and the save both use it.

**Inputs:** up to N games, where N is 1, 3 or 5 from `match_format`. Each game is a pair of whole numbers (0–99) or blank.

**Which game rows are shown**
- Game 1 is always shown.
- In best of 3, Game 3 shows only once Games 1 and 2 are both filled and split 1–1.
- In best of 5, Games 4 and 5 show only when the match isn't decided after the earlier games:
  - Game 4 shows once Games 1–3 are filled and neither team has 3 wins.
  - Game 5 shows once Games 1–4 are filled and it's 2–2.
- Games 2 and 3 of best of 5 show from the start (*my call*, the way Game 2 of best of 3 does), since at least 3 games are always played.
- A hidden game's values are ignored and not saved.

**Single-game rule** (T = `points_to_win`, W = winner's points, L = loser's points):

| Setting | Valid final score | Message when it fails |
| --- | --- | --- |
Check these in order and show the first message that applies:

| Check | Fails when | Message |
| --- | --- | --- |
| 1 (any setting) | W = L | "A game can't end in a tie — {W}–{L}." |
| 2 (any setting) | W < T | "Games to {T} end when a team reaches {T} — {W}–{L} isn't a final score." |
| 3 (win by 2 on) | not (W = T and L ≤ T − 2) and not (W > T and W − L = 2) | "Games to {T} must be won by 2 — {W}–{L} isn't a final score." |
| 4 (win by 2 off) | W > T | "Games to {T} end at {T} — {W}–{L} isn't a final score." |

Show one message per bad game, prefixed "Game {n}: ".
- Check 1 (a tie) blocks everyone, admins included (*my call*, following option A: a tied game has no winner to count).
- Checks 2–4 block players. For admins they are warnings.

**Match rules**
- Best of 1, 3 or 5 is decided when one team wins 1, 2 or 3 games.
- **Half-filled game** (one box filled, one blank): "Game {n}: enter both scores." This blocks everyone, admins included.
- **Blank game before a filled one** (e.g. Game 1 blank, Game 2 filled): "Game {n}: enter both scores." This blocks everyone.
- **Trailing blank games** (every shown game after the last filled one is fully blank):
  - Players: blocked, with "Game {n}: enter both scores." for the first blank shown game.
  - Admins: allowed. The blank games aren't saved. This is how a timed night that stopped early gets recorded (owner's decision).
  - Example: a best-of-3 night where only Game 1 was played (11–7) can be saved by an admin as "Dinkers win 1–0", with one `GameScore` row.
- After the match is decided, any later shown game would have been hidden by the rows rule above, so it can't happen.
- **Too few games, so nobody has clinched yet:** "A best-of-3 match ends when one team wins 2 games." (best-of-5 says "3 games"). This blocks players. For admins it is a warning with Save anyway, as long as one team leads on games won (option A).
  - Examples: 1–0 after one game in a best-of-3, or 2–1 after three games in a best-of-5.
- **No team leads** (games won are equal, e.g. 1–1, or 0–0 with all blank): "Enter games until one team is ahead." This blocks everyone, admins included.

**Result line:** shown when the games entered give a leader.
- "{Team} win {a}–{b}" (games won), or for a single game "{Team} win {W}–{L}".
- On a forfeit: "{Team} win by forfeit".

**Who is blocked**
- Players: any message blocks Save. Save is disabled while messages show, and the server refuses the save anyway.
- Admins: the per-game points messages (checks 2–4) and the "not decided" message are warnings, and Save becomes **Save anyway**. Trailing blank games give no message for admins.
- Everyone: a tied game, a half-filled game, a blank game before a filled one, and no leader all block Save.

**What a save writes** (in one transaction, after `Event.objects.select_for_update()`):
- Replace the match's `GameScore` rows with the shown, filled games (`game_no` 1..n).
- Set `winner` to the team with more games won, `forfeited_by=None`, `status=final` and `last_edited_by=request.user`.
- Re-check permissions and the match's state inside the lock. A player save that arrives after an admin locked the match is refused with "An admin has already scored this match."

**Forfeit** (admins only, *my call*; the P8 mock shows the button but the PRD gives no player permission):
- Choose the team that forfeited.
- Delete `GameScore`s, then set `forfeited_by` to that team, `winner` to the other, `status=final` and `last_edited_by`.

**Clear score** (admins only):
- Confirm inline: "Clear the score for {A} vs {B}? The match goes back to unscored."
- Delete `GameScore`s, then set `winner=None`, `forfeited_by=None`, `status=scheduled` and `last_edited_by=request.user`. The match stays admin-locked, so players can't re-enter it (as played back to the owner).
- If it was the event's last score, setup and regenerate unlock again (`Event.has_scores()` already reads this).

**Toasts:** "Score saved", "Forfeit saved", "Score cleared".

## 6. The sheet

```
Cancel                       Wk 2 · R1 · Court 1
Enter score
Best of 3 · games to 11 · win by 2
            ▌Dinkers   ▌Smashers
Game 1      [11]✓      [ 7]
Game 2      [ 9]       [11]✓
Game 3      [11]       [ – ]
[ Dinkers win 2–1 ]          (teal band)
Game 3: Games to 11 must be won by 2 — 11–10 isn't a final score.   (red for players, amber for admins)
Mark forfeit · Clear score            (admins only)
[          Save score          ]   (Coral, Indigo text; "Save anyway" for admin warnings)
```

**Layout**
- The header has the match context and the format line, e.g. "Best of 3 · games to 11 · win by 2" (or "win by 1" when off).
- Two columns of score boxes. Each box is 54×44 with a large bold number, `inputmode="numeric"`, `pattern="[0-9]*"`, `autocomplete="off"`, and a Cobalt focus ring. The winning number of each game turns teal (design spec §6.5).
- The footer is sticky, with the primary button.
- On a phone the sheet is full screen. On a laptop it is a centered dialog.

**Live check:**
- When a box changes (on `change`, not every keystroke, so the page doesn't jump while typing), HTMX posts the form to a check URL.
- That URL re-renders the form body: the rows shown, ticks, the result line, messages and the button label. The input the user is in keeps focus. Swapping only the parts below the inputs, or using `hx-preserve` or a focus-safe swap, is the builder's call.

**Saving:**
- Save posts the form.
- On success the sheet closes and the card on the page is replaced by its updated version. Out-of-band swap of `[data-card=…]` or a re-render of `#event-body` is the builder's call.
- On refusal the sheet re-renders with the messages.

**Mark forfeit:**
- Opens a short choice inside the sheet: "Which team forfeited? ( ) Dinkers ( ) Smashers", then [Save forfeit] and [Back].

**Without JS:**
- "Enter score" is a plain link to the score page.
- The page renders the same form body in `base_app.html`.
- Saving or clearing redirects back to the event Schedule tab at the match's week (`?week=N`), with the toast.
- Without JS, every game row of the format is shown, since there's no live check. Rows the rules would hide are ignored even if filled. Trailing blank rows follow the trailing-blank rule (allowed for admins, blocked for players).

**URLs** (names are *my call*), each under `@login_required`, with the event fetched within the user's organization:

| URL | Name | Purpose |
| --- | --- | --- |
| `/events/<id>/matches/<match_id>/score/` | `match_score` | GET form (sheet partial for HTMX, full page otherwise); POST save |
| `…/score/check/` | `match_score_check` | POST, returns the re-rendered form body |
| `…/score/forfeit/` | `match_forfeit` | POST, admins only |
| `…/score/clear/` | `match_score_clear` | POST, admins only; without `confirm=1` it re-renders with the confirm box |

## 7. The match card

- **Unscored, and the viewer may score it:** a full-width **Enter score** button (Coral, Indigo text) at the foot of the card.
- **Scored:** the chips as now. Below them, "Last edited by {name}" in muted small text, plus **Edit score** when the viewer may edit.
- `{name}` is the editor's player name if they have one, otherwise their full name, otherwise their email (*my call*).
- **Never on share pages.** `build_page` gains the viewer's permissions, or the view passes a `can_score` set of match ids (builder's call). With a token, it is always empty.
- Tonight and the Schedule tab use the same card, so both get the button.

## 8. Testing

- **Rules module, table-driven:**
  - every format, with to 11, 15 and 21 and win by 2 on and off;
  - deuce scores (to 11 with win by 2 on: 13–11 valid, 14–11 and 12–11 invalid; with it off: 11–10 valid, 12–11 invalid);
  - ties (block admins too), half-filled games, a blank game before a filled one;
  - trailing blank games: a player is blocked, an admin saves 1–0 in a best-of-3 with one `GameScore` row;
  - Game 3 and Games 4–5 appearing only when needed;
  - player versus admin blocking, and the no-leader block for admins;
  - the result-line text.
- **Views:**
  - the who-can-score table (§4), row by row;
  - A9: admin save, then a player is refused, including inside the lock;
  - save, forfeit and clear write exactly the fields in §5;
  - clearing the last score unlocks setup;
  - HTMX versus full page;
  - no-JS redirect to `?week=N`;
  - no buttons on share pages;
  - a cancelled week, a void match, a withdrawn team and a draft event all refuse.
- **End to end:** seed with `--tonight`, then:
  - an admin scores a best-of-3 match on Tonight;
  - a player scores their own match with player entry on and is refused after an admin edit;
  - an admin forfeits a match, then clears it.
- **Browser check at 390 px:** the sheet fills the screen, the boxes bring up the number pad, nothing scrolls sideways, and the card updates in place.

## 9. Left to the builder

- Module and template names. How the dialog is opened and closed (native `<dialog>` with an HTMX attribute or Basecoat's dialog styles; no JS file).
- The exact focus-safe swap for the live check, and the card swap after save.
- Whether permissions are computed in `build_page` or the view.
