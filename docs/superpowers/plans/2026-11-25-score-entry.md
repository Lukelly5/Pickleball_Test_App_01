# Slice 5: Score entry (P8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins, and players on the match when the event allows it, enter, edit, forfeit and clear match scores from the event page's match cards. The form is a phone-first sheet that the server keeps up to date.

**Architecture:** The work is split into four layers:
- **Rules** (`league/scoring.py`, new): pure Python with no Django models. It turns raw form strings into a `ScoreCheck`: the rows to show, the game winners, the messages, the result line, and whether the viewer may save.
- **Writes and permissions** (`league/score_edits.py`, new): `can_score` and `scorable_ids`, plus `save_score`, `save_forfeit` and `clear_score`. Each write runs behind the Event row lock.
- **Views** (`league/score_views.py`, new):
  - the full-page form, which is the no-JS path;
  - the sheet partial, the check endpoint, and the forfeit and clear endpoints.
- **Card** (`templates/league/event/_card.html` and `league/schedule_page.py`): "Last edited by", and the Enter or Edit score button when the viewer may score.

**Tech Stack:** Python 3.13, Django 6.1, HTMX 2.0.11 (vendored), Basecoat 1.1.0 + Tailwind via django-tailwind-cli 4.8.3, pytest 9 + pytest-django 4.14.

**Spec:** `docs/superpowers/specs/2026-11-25-score-entry-design.md`. Also PRD §3 Flow B and §5 P8, and the front-end spec `docs/superpowers/specs/2026-11-19-front-end-design-system-design.md` (§6.5 modal/sheet, score input and match card; §7 P8 mock).

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

**Locking (carry-forward memory, A13):** every score write (save, forfeit, clear) runs inside `transaction.atomic()` and starts with `Event.objects.select_for_update().get(pk=…)`. It then re-reads the match and re-checks permissions under that lock.

**Today:** only views call `django.utils.timezone.localdate()`. Rules and permission functions take `today: date`.

**Access**
- All score URLs are `@login_required`.
- The event is fetched with `league.event_views.member_event` (404 for another org) and goes through `draft_guard`.
- The match is fetched with `get_object_or_404(Match, pk=match_pk, flight__division__event=event)`.
- A same-org user who may not score it gets 403 (`PermissionDenied`).
- Forfeit and clear are admin-only (403 for players).

**HTMX:** the same rule as Slice 4. Return a partial only when `HX-Request` is set and `HX-History-Restore-Request` is not, and add `patch_vary_headers(response, ["HX-Request", "HX-History-Restore-Request"])`.

**JS:** no JS file and no new library. HTMX attributes only, `hx-on` included.

**Confirms:** use the existing inline amber `role="alert"` box. A POST without `confirm=1` re-renders the box with a confirm button and a cancel link. Never use `confirm()`.

**Copy, verbatim (from the spec)**

Rule messages:
- "Game {n}: A game can't end in a tie — {W}–{L}."
- "Game {n}: Games to {T} end when a team reaches {T} — {W}–{L} isn't a final score."
- "Game {n}: Games to {T} must be won by 2 — {W}–{L} isn't a final score."
- "Game {n}: Games to {T} end at {T} — {W}–{L} isn't a final score."
- "Game {n}: enter both scores."
- "A best-of-3 match ends when one team wins 2 games." / "A best-of-5 match ends when one team wins 3 games."
- "Enter games until one team is ahead."
- Plan's call: "Game {n}: scores must be whole numbers from 0 to 99."

Results and refusals:
- Result line: "{Team} win {a}–{b}". For a single game it is "{Team} win {W}–{L}", and on a forfeit "{Team} win by forfeit".
- "An admin has already scored this match."

Format line:
- "Best of 3 · games to 11 · win by 2". Use "1 game" for single, and "win by 1" when win by 2 is off.

Buttons and labels:
- "Enter score", "Edit score", "Save score", "Save anyway", "Cancel"
- "Mark forfeit", "Which team forfeited?", "Save forfeit", "Back"
- "Clear score", "Clear the score for {A} vs {B}? The match goes back to unscored."
- "Last edited by {name}"

Toasts:
- "Score saved", "Forfeit saved", "Score cleared"

**Score inputs:** 54×44 boxes with a large bold number, `inputmode="numeric"`, `pattern="[0-9]*"`, `autocomplete="off"` and a Cobalt focus ring. Field names are `g{n}a` and `g{n}b`, and ids are `score-g{n}a` and `score-g{n}b`. The ids must stay stable across swaps so htmx can restore focus.

## Review Focus

1. **Junk in a score box.** For example "abc", "-3", "100", "11.5" or " 7 ". The person should see "Game {n}: scores must be whole numbers from 0 to 99." Nothing is saved, and there's no 500. Leading and trailing spaces are fine. Pinned in Task 1 (`test_junk_input`).
2. **A stale sheet.** The match was deleted by a regenerate after the sheet opened. The save should show `league.schedule_edits.GONE` and must not crash. Pinned in Task 2 (`test_save_gone_match`).
3. **A tampered URL.** Posting a score to a match id from another event, or from another org, should give a 404 and change nothing. Pinned in Task 3 (`test_match_from_other_event_404`).
4. **Editing down.** A 3-game best-of-3 score edited to 2–0 should leave exactly 2 `GameScore` rows, with the old Game 3 gone. Pinned in Task 2 (`test_edit_replaces_games`).
5. **Forfeit, then real scores.** Forfeiting a match and then saving real scores should clear `forfeited_by`, and the card should show chips, not "Forfeit". Pinned in Task 2 (`test_save_after_forfeit_clears_forfeit`).

---

### Task 1: The score rules

**Files:**
- Create: `league/scoring.py`
- Test: `tests/test_scoring.py` (new)

**Interfaces:**
- Produces, all in `league/scoring.py`. It does not import `league.models`.

```python
@dataclass(frozen=True)
class Format:
    best_of: int            # 1, 3 or 5
    points_to_win: int      # 11, 15 or 21
    win_by_two: bool
    @classmethod
    def of(cls, event) -> "Format"   # match_format "single"→1, "best_of_3"→3, "best_of_5"→5
    @property
    def label(self) -> str           # "Best of 3 · games to 11 · win by 2" / "1 game · games to 15 · win by 1"

@dataclass(frozen=True)
class Message:
    text: str
    blocking: bool          # True: blocks Save for this viewer; False: admin warning

@dataclass(frozen=True)
class ScoreCheck:
    shown: int                          # rows to show (1..best_of)
    values: tuple[tuple[str, str], ...] # the raw strings of every row 1..best_of, stripped (for re-rendering)
    game_winners: tuple[str | None, ...]  # per shown row: "a", "b" or None (blank/half/tie/junk)
    wins: tuple[int, int]               # games won among shown rows
    leader: str | None                  # "a" | "b" | None
    messages: tuple[Message, ...]
    result: str                         # "" when no leader
    @property
    def can_save(self) -> bool          # no blocking message
    @property
    def save_anyway(self) -> bool       # can_save and messages present (only possible for admins)
    def games_to_save(self) -> list[tuple[int, int]]  # filled shown rows in order, as ints

def raw_games(data, best_of: int) -> list[tuple[str, str]]   # reads data.get("g{n}a", ""), data.get("g{n}b", ""), n = 1..best_of
def check_score(fmt: Format, raw: list[tuple[str, str]], names: tuple[str, str], *, admin: bool) -> ScoreCheck
```

**Rules:** see spec §5 for every rule and message. These are the decisions the spec leaves to the plan:
- **Parsing.** Strip each value. A blank string means blank. Anything that isn't `^\d{1,2}$` is junk. Junk gives "Game {n}: scores must be whole numbers from 0 to 99." and blocks everyone. A junk row counts as neither blank nor filled for the row logic: it is not a winner, and it does not end the "trailing blanks".
- **Game winner** for counting and for the teal highlight: the higher of the two filled numbers, even when the points checks fail. That way an admin's 9–7 counts. A tie gives `None`.
- **Shown rows:**
  - Best of 1 shows 1 row.
  - Best of 3 shows 2 rows. A 3rd row is added when Games 1 and 2 are both filled with winners and split 1–1.
  - Best of 5 shows 3 rows. A 4th row is added when Games 1–3 are filled with winners and nobody has 3 wins. A 5th is added when Games 1–4 are filled with winners and it's 2–2.
  - Rows beyond `shown` are ignored, even if they're filled.
- **Message order:** per game, in row order (junk, then half-filled or blank-before-filled, then the points checks 1–4 from spec §5). Then the player's trailing-blank message. Then the match-level message ("not decided" or "no leader").
- **Blocking:**
  - Players: everything blocks.
  - Admins: points checks 2–4 and "not decided" are warnings (`blocking=False`).
  - Admins: tie, junk, half-filled, blank-before-filled and no-leader all block.
  - Admins get no trailing-blank message.
- **Result line:** best of 1 uses the points (`"{name} win 11–7"`); best of 3 and 5 use games won (`"{name} win 2–1"`). The name is `names[0]` for "a" and `names[1]` for "b".

- [ ] **Step 1: Write the failing tests** in `tests/test_scoring.py`. Use `B3 = Format(3, 11, True)`, `B1 = Format(1, 11, True)`, `B5 = Format(5, 11, True)`, `NAMES = ("Dinkers", "Smashers")`, and `chk(fmt, *pairs, admin=False)`, which pads the pairs with `("", "")` up to `best_of` and calls `check_score`.

```python
@pytest.mark.parametrize("t,wb2,a,b,ok", [
    (11, True, 11, 9, True), (11, True, 11, 10, False), (11, True, 13, 11, True), (11, True, 14, 11, False),
    (11, True, 12, 11, False), (11, True, 9, 7, False), (11, False, 11, 10, True), (11, False, 12, 11, False),
    (15, True, 15, 13, True), (21, True, 21, 19, True), (21, True, 20, 18, False), (11, True, 0, 11, True),
])
def test_single_game_rule(t, wb2, a, b, ok): assert chk(Format(1, t, wb2), (str(a), str(b))).can_save is ok

def test_messages_verbatim():
    assert chk(B1, ("11", "10")).messages[0].text == "Game 1: Games to 11 must be won by 2 — 11–10 isn't a final score."
    assert chk(B1, ("9", "9")).messages[0].text == "Game 1: A game can't end in a tie — 9–9."
    assert chk(B1, ("9", "7")).messages[0].text == "Game 1: Games to 11 end when a team reaches 11 — 9–7 isn't a final score."
    assert chk(Format(1, 11, False), ("12", "10")).messages[0].text == "Game 1: Games to 11 end at 11 — 12–10 isn't a final score."
def test_rows_best_of_3(): assert chk(B3).shown == 2; assert chk(B3, ("11","7"), ("7","11")).shown == 3; assert chk(B3, ("11","7"), ("11","5")).shown == 2
def test_rows_best_of_5(): assert chk(B5).shown == 3; 2-1 after three → 4; 3-0 → 3; 2-2 after four → 5; 3-1 after four → 4
def test_hidden_row_ignored(): c = chk(B3, ("11","7"), ("11","5"), ("11","3")); assert c.shown == 2 and c.games_to_save() == [(11,7), (11,5)] and c.result == "Dinkers win 2–0"
def test_result_lines(): assert chk(B1, ("7","11")).result == "Smashers win 11–7"; assert chk(B3, ("11","7"),("9","11"),("11","5")).result == "Dinkers win 2–1"
def test_game_winners_for_teal(): assert chk(B3, ("11","7"), ("9","11")).game_winners == ("a", "b", None)
def test_player_trailing_blank_blocked(): c = chk(B3, ("11","7")); assert not c.can_save and "Game 2: enter both scores." in [m.text for m in c.messages]
def test_admin_saves_one_nil():  # owner's decision
    c = chk(B3, ("11","7"), admin=True); assert c.can_save and c.save_anyway and c.games_to_save() == [(11, 7)]
    assert [m.text for m in c.messages] == ["A best-of-3 match ends when one team wins 2 games."] and c.result == "Dinkers win 1–0"
def test_admin_timed_game_warning(): c = chk(B1, ("9","7"), admin=True); assert c.can_save and c.save_anyway
def test_tie_blocks_admin(): assert not chk(B1, ("9","9"), admin=True).can_save
def test_no_leader_blocks_admin(): c = chk(B3, ("11","7"), ("7","11"), admin=True); assert not c.can_save and c.messages[-1].text == "Enter games until one team is ahead."
def test_all_blank_blocks_admin(): assert not chk(B3, admin=True).can_save
def test_half_filled_blocks_admin(): assert "Game 1: enter both scores." in [m.text for m in chk(B3, ("11",""), admin=True).messages]
def test_blank_before_filled_blocks_admin(): assert not chk(B3, ("",""), ("11","5"), admin=True).can_save
def test_best_of_5_not_decided_text(): "A best-of-5 match ends when one team wins 3 games." in chk(B5, ("11","7"),("11","7"),("7","11"), admin=True) messages
@pytest.mark.parametrize("junk", ["abc", "-3", "100", "11.5", "1e1"])
def test_junk_input(junk):  # Review Focus 1
    c = chk(B1, (junk, "7"), admin=True); assert not c.can_save and c.messages[0].text == "Game 1: scores must be whole numbers from 0 to 99."
def test_spaces_trimmed(): assert chk(B1, (" 11 ", "7")).can_save
def test_format_label(): Format(3, 11, True).label == "Best of 3 · games to 11 · win by 2"; Format(1, 15, False).label == "1 game · games to 15 · win by 1"
def test_raw_games_reads_fields(): raw_games(QueryDict("g1a=11&g1b=7"), 3) == [("11","7"), ("",""), ("","")]
```

- [ ] **Step 2: Run them and check they fail** (ImportError).
- [ ] **Step 3: Implement** `league/scoring.py`.
- [ ] **Step 4: Run the full suite.** Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): score rules for every match format`

---

### Task 2: Permissions and score writes

**Files:**
- Create: `league/score_edits.py`
- Test: `tests/test_score_edits.py` (new)

**Interfaces:**
- Consumes: `Format`, `check_score`, `ScoreCheck` (Task 1); `league.schedule_edits.GONE`; `accounts.roles.player_for`.
- Produces, in `league/score_edits.py`:

```python
class ScoreRefused(Exception): ...          # str(exc) is the user-facing message
def editor_name(user) -> str                # linked Player name (user.player), else user.get_full_name(), else user.email; "" for None
def admin_locked(match) -> bool             # match.last_edited_by_id and match.last_edited_by.is_admin
def can_score(user, match, today: date) -> bool
def can_manage(user, match) -> bool         # forfeit/clear: user.is_admin and _playable(match), same org
def scorable_ids(user, event, match_ids: Iterable[int], today: date) -> frozenset[int]   # the subset that can_score; one query for the matches (select_related week, teams, last_edited_by) plus at most one for the player's teams
def save_score(event, match_id: int, user, raw: list[tuple[str, str]], today: date, *, anyway: bool = False) -> tuple[Match | None, ScoreCheck]
def save_forfeit(event, match_id: int, user, forfeited_team_id: int) -> Match
def clear_score(event, match_id: int, user) -> Match
```

**Rules** (spec §4 and §5):
- `_playable(match)`, shared by everyone:
  - the event status is published or completed;
  - the week isn't cancelled;
  - the match status is `scheduled` or `final`;
  - neither team is withdrawn.
- `can_score`:
  - **Admins** of the event's org: `_playable`.
  - **Players:** all of these hold:
    - `_playable`;
    - the event is published;
    - `player_score_entry` is on;
    - `player_for(user)` is a member of `team_a` or `team_b`;
    - `week.date is None or week.date <= today`;
    - the match isn't `admin_locked`.
- `save_score`:
  - Lock the event, then re-fetch the match by `pk` within the event (missing: `ScoreRefused(GONE)`).
  - If `not can_score(...)` and the match is `admin_locked` and the user isn't an admin: `ScoreRefused("An admin has already scored this match.")`. Any other refusal: `PermissionDenied`.
  - Run `check_score(Format.of(event), raw, (team_a.name, team_b.name), admin=user.is_admin)`. Return `(None, check)` and write nothing when `not check.can_save`, or when `check.save_anyway and not anyway`.
  - Otherwise delete the `GameScore`s, `bulk_create` the `games_to_save()` as `game_no` 1..n, and set `winner`, `forfeited_by=None`, `status=final` and `last_edited_by=user`. Return `(match, check)`.
- `save_forfeit`:
  - Admin-only; same lock and re-fetch.
  - `forfeited_team_id` must be `team_a_id` or `team_b_id`, otherwise `ScoreRefused("Choose the team that forfeited.")`.
  - Delete the games, then set `forfeited_by`, `winner` (the other team), `status=final` and `last_edited_by`.
- `clear_score`:
  - Admin-only; same lock and re-fetch.
  - Delete the games, then set `winner=None`, `forfeited_by=None`, `status=scheduled` and `last_edited_by=user`.

- [ ] **Step 1: Write failing tests** in `tests/test_score_edits.py`.
  - Fixture `league`: `make_event(weeks=4, courts=3, status=PUBLISHED, match_format="best_of_3")`, 4 teams ("Dinkers", "Smashers", "Lobsters", "Kings"), then `generate_event`.
  - Week 2 is dated `TODAY = date(2027, 3, 9)` (factory dates). Tests pass `today=TODAY`.
  - Helpers: `admin` (`admin_of`); `player_on(match)`, a `User` linked to a player of `match.team_a`; `m2`, a week-2 match.

```python
def test_admin_can_score_any_week(league): admin can_score on a week-4 match with today=TODAY
def test_player_needs_entry_on(league): player_score_entry False → can_score False; True → True
def test_player_not_on_match(league): player of a team not in m2 → False
def test_player_future_week(league): player on a week-3 match, today=TODAY → False; undated week (date=None) → True
def test_not_playable(league): cancelled week / match status void / team withdrawn / event draft → False for admin and player
def test_player_locked_after_admin(league): admin save_score m2 → player can_score False
def test_save_writes_fields(league):
    m, chk = save_score(league, m2.pk, admin, [("11","7"),("9","11"),("11","5")], TODAY)
    games = list(m.games.values_list("game_no","points_a","points_b")); assert games == [(1,11,7),(2,9,11),(3,11,5)]
    assert m.winner_id == m.team_a_id and m.status == "final" and m.forfeited_by_id is None and m.last_edited_by == admin
def test_admin_saves_one_nil(league): save_score(..., admin, [("11","7"),("",""),("","")], TODAY, anyway=True) → one GameScore, winner team_a
def test_save_anyway_needs_flag(league): same call without anyway → (None, chk) with chk.save_anyway, nothing written
def test_player_blocked_writes_nothing(league): player save [("11","10"),...] → (None, chk) and m2.games.count() == 0
def test_player_refused_after_admin(league): admin saves; player save → ScoreRefused("An admin has already scored this match.")
def test_save_gone_match(league):  # Review Focus 2
    pk = m2.pk; Match.objects.filter(pk=pk).delete(); with pytest.raises(ScoreRefused, match="no longer on the schedule"): save_score(league, pk, admin, ..., TODAY)
def test_edit_replaces_games(league):  # Review Focus 4
    save 3 games, then save [("11","7"),("11","5"),("","")] → m2.games.count() == 2
def test_save_after_forfeit_clears_forfeit(league):  # Review Focus 5
    save_forfeit(team_b); save_score(...) → forfeited_by_id None, games present
def test_forfeit(league): save_forfeit(league, m2.pk, admin, m2.team_b_id) → forfeited_by team_b, winner team_a, games 0, status final
def test_forfeit_player_denied(league): PermissionDenied
def test_forfeit_wrong_team(league): ScoreRefused("Choose the team that forfeited.")
def test_clear(league): save then clear_score → games 0, winner None, forfeited_by None, status "scheduled", last_edited_by admin; player can_score still False
def test_clear_last_score_unlocks(league): save then clear → league.has_scores() is False
def test_editor_name(league): linked player → player name; plain admin with first/last name → full name; else email
def test_scorable_ids(league): player with entry on → exactly the ids of today's-or-earlier matches of their team
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement** `league/score_edits.py`.
- [ ] **Step 4: Run the full suite.** Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): score permissions, save, forfeit and clear behind the event lock`

---

### Task 3: The score page (no-JS path) and card buttons

**Files:**
- Create: `league/score_views.py`
- Modify: `league/urls.py`
- Modify: `league/schedule_page.py`:
  - add `last_edited_name: str` to `Card`, and a property `scored -> bool` (chips present, a forfeit, or status `final`);
  - make `_card` public as `card_for(match, my_team_ids) -> Card`;
  - add `select_related("last_edited_by__player")` to the match query.
- Modify: `league/event_views.py`. `render_schedule` adds `scorable` (a frozenset of match ids, empty with a token) to the context, computed with `scorable_ids(request.user, event, [c.match_id for r in page.rounds for c in r.cards], today)`.
- Create: `templates/league/score/page.html` (full page in `base_app.html`, title "Enter score"), `templates/league/score/_form.html` (header, format line, game rows, result, messages, buttons), and `templates/league/score/_forfeit.html`.
- Modify: `templates/league/event/_card.html`, to add the "Last edited by" line and the button.
- Test: `tests/test_score_views.py` (new). Also extend `tests/test_schedule_page.py` with `last_edited_name` and `scored`.

**Interfaces:**
- Consumes: Tasks 1–2; `member_event`, `draft_guard` and `_render` from `league/event_views.py`.
- Produces: URL names, all under `events/<int:pk>/matches/<int:match_pk>/score/`:
  - `match_score`: `score/`, GET form and POST save;
  - `match_score_check`: `score/check/`, POST;
  - `match_forfeit`: `score/forfeit/`, POST; GET shows the forfeit choice;
  - `match_score_clear`: `score/clear/`, POST.

  Task 4 relies on these view behaviors:
  - `render_score(request, event, match, check: ScoreCheck | None, *, step: str = "form", confirm: str | None = None, status=200)` renders `league/score/_form.html` (or `_forfeit.html` when `step="forfeit"`) inside `page.html`, or alone for HTMX.
  - `check=None` means a fresh form: the values are the current saved games, and no messages show.

**Behavior (no JS):**
- **GET `match_score`:**
  - Without JS, every format row is shown.
  - The values come from the saved games.
  - Save is labelled "Save score", or "Save anyway" when `check.save_anyway`.
  - For a player, Save is `disabled` while `check` has messages.
  - Admins see "Mark forfeit" (a link to the forfeit GET) and "Clear score" (a POST button), but Clear only when the match is scored.
  - Cancel links back to the schedule.
- **POST save:**
  - On success: `messages.success("Score saved")`, then a redirect to `reverse("event_schedule", args=[event.pk]) + f"?week={match.week.number}"`.
  - When the rules block: re-render with the messages, status 200.
  - On `ScoreRefused`: re-render with the message as a blocking message.
- **Forfeit:**
  - GET shows "Which team forfeited?" with two radio buttons (`team`), "Save forfeit" and "Back".
  - POST saves, toasts "Forfeit saved" and redirects to `?week=N`.
- **Clear:**
  - POST without `confirm=1` re-renders with the confirm box.
  - With `confirm=1` it clears, toasts "Score cleared" and redirects to `?week=N`.
- **Card:**
  - When `card.last_edited_name` is set, show "Last edited by {name}" in muted small text.
  - When `card.match_id in scorable`, show a full-width button (Coral, `text-ink`) at the foot, linking to `match_score`. It reads "Edit score" when `card.scored`, otherwise "Enter score".

- [ ] **Step 1: Write failing tests** in `tests/test_score_views.py`.
  - Fixture: as `tests/test_event_schedule.py::league`, but with `match_format="best_of_3"` and `player_score_entry=True`.
  - Week 2 is dated `timezone.localdate()`, the others 7 days apart.
  - `m2` is a week-2 match. `score_url(m)` gives `/events/{pk}/matches/{m.pk}/score/`.

```python
def test_card_has_enter_score_for_admin(client, league): schedule week 2 html contains f'href="{score_url(m2)}"' and "Enter score"
def test_card_no_button_for_other_player(client, league): player on another team → that card has no score link
def test_share_page_has_no_score_button(client, league): share page html has no "/matches/" and no "Enter score"
def test_form_shows_format_and_rows(client, league): GET → "Best of 3 · games to 11 · win by 2", inputs score-g1a..score-g3b, 'inputmode="numeric"'
def test_save_redirects_to_week(client, league): POST g1a=11&g1b=7&g2a=11&g2b=5 → 302 Location ends "?week=2", toast "Score saved", m2 final
def test_save_blocked_rerenders(client, league): player POST g1a=11&g1b=10&g2a=11&g2b=5 → 200 with "Game 1: Games to 11 must be won by 2 — 11–10 isn&#x27;t a final score." (or unescaped), nothing saved
def test_admin_save_anyway_two_taps(client, league): admin POST g1a=9&g1b=7&g2a=11&g2b=5 → 200 with "Save anyway" and the warning, nothing saved; same POST + anyway=1 → 302, saved
def test_card_after_save(client, league): admin saves → schedule shows "Last edited by" and "Edit score", chips 11 and 7
def test_forfeit_flow(client, league): GET forfeit → "Which team forfeited?"; POST team=<b> → 302, toast "Forfeit saved", card shows "Forfeit · {team_a} wins"
def test_clear_confirm(client, league): save; POST clear {} → "Clear the score for"; POST confirm=1 → 302, toast "Score cleared", m2 unscored
def test_player_forfeit_and_clear_403(client, league)
def test_other_org_404(client, league); def test_same_org_non_member_403(client, league)
def test_match_from_other_event_404(client, league):  # Review Focus 3: match pk of another event in the URL of this event → 404, nothing saved
def test_draft_event_redirects_admin_to_preview(client, league)
def test_cancelled_week_403(client, league)
def test_anonymous_redirects_to_login(client, league)
```

**"Save anyway" is a deliberate second tap** (see Task 2's `anyway` flag):
- When the form is rendered with `check.save_anyway`, the primary button reads "Save anyway" and posts `anyway=1`.
- Without JS, an admin's first POST with only warnings re-renders with the warnings and that button. The second tap saves.

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement** the views, URLs, templates and card changes.
- [ ] **Step 4: Run** `tailwind build`, then the full suite. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): score page, forfeit and clear, with card buttons`

---

### Task 4: The live sheet (HTMX)

**Files:**
- Modify: `templates/league/event/page.html`. Logged-in pages only (not `share`) get `<dialog id="score-sheet" …>`: full-screen on a phone (`max-md:` full width and height, no margin), a centered card on `md`.
- Modify: `templates/league/event/_card.html`. The score button gets `hx-get="{{ score url }}" hx-target="#score-sheet" hx-swap="innerHTML" hx-on::after-request="document.getElementById('score-sheet').showModal()"`, and keeps its `href` for no-JS.
- Modify: `templates/league/score/_form.html`, `_forfeit.html`, and `league/score_views.py`.
- Test: `tests/test_score_sheet.py` (new)

**Interfaces:**
- Consumes: Task 3's URLs and `render_score`.

**Behavior:**
- **GET `match_score` with HTMX** returns the sheet partial. It has:
  - a header: Cancel (`hx-on:click` closes the dialog), "Enter score" or "Edit score", and "Wk {n} · R{r} · Court {c}";
  - the format line;
  - a `<form id="score-form">` with `hx-post` to `match_score`;
  - inside the form, `<div id="score-body">` holding the rows, result, messages and buttons.

  The rows follow `check.shown`, using live rows rather than all rows. On a fresh form, compute `check_score` from the saved values with messages hidden.
- **Live check.** Each input has `hx-post="{check url}" hx-trigger="change" hx-target="#score-body" hx-select="#score-body" hx-swap="outerHTML" hx-include="#score-form"`. The check endpoint returns `#score-body` re-rendered with messages shown. Inputs keep their ids (`score-g{n}a` / `score-g{n}b`), so htmx restores focus after the swap.
- **Highlighting:**
  - The winning number of each game gets `bg-progress text-ink` (from `check.game_winners`).
  - The result line is a teal band (`bg-progress text-ink`).
  - Blocking messages are red (`text-danger`). Admin warnings are amber (`bg-warn-bg text-warn`).
- **Save success with HTMX:**
  - The response has status 200, the header `HX-Trigger: score-saved`, and a body holding the updated card with `hx-swap-oob="outerHTML:[data-card='{id}']"`.
  - The dialog has `hx-on:score-saved="this.close()"`.
  - The card is rendered with `card_for(match, my_team_ids)` and this viewer's `scorable`.
  - The toast goes through `messages` as on the full page. The existing toast region must show it after an HTMX response; check how `base.html` renders messages, and include the toast markup out-of-band if needed.
- **Save refused or blocked with HTMX:** re-render the sheet body in place.
- **Forfeit and clear with HTMX:** they work inside the sheet the same way. "Mark forfeit" uses `hx-get` with the forfeit step into `#score-sheet`. Success sends `score-saved` plus the out-of-band card.

- [ ] **Step 1: Write failing tests** with `HX-Request: true` (same fixture as Task 3).

```python
def test_sheet_partial(client, league): GET htmx → no "<html", has 'id="score-form"', "Wk 2 · R{r} · Court {c}", shows 2 rows (score-g3a absent) for a fresh best-of-3
def test_check_shows_game_3(client, league): POST check g1a=11&g1b=7&g2a=7&g2b=11 → 'id="score-g3a"' present, no "<html"
def test_check_result_and_teal(client, league): POST check g1a=11&g1b=7&g2a=11&g2b=5 → "Dinkers win 2–0" (team_a name) and 'bg-progress'
def test_check_player_message_and_disabled(client, league): player POST check g1a=11&g1b=10 → message text present and Save has "disabled"
def test_htmx_save_returns_oob_card(client, league): POST save htmx → 200, r["HX-Trigger"] == "score-saved", f"hx-swap-oob" and f"data-card=\"{m2.pk}\"" in body, "Edit score" in body
def test_htmx_save_blocked_stays_in_sheet(client, league): blocked POST → no HX-Trigger, 'id="score-body"' in body
def test_card_button_has_hx_and_href(client, league): schedule html card button has both href=score_url and hx-get=score_url, hx-target="#score-sheet"
def test_no_dialog_on_share_page(client, league): 'id="score-sheet"' not in share html
def test_vary_header(client, league): GET score page → "HX-Request" in r["Vary"]
```

- [ ] **Step 2: Run them and check they fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `tailwind build`, then the full suite. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(league): live score sheet with in-place card update`

---

### Task 5: Walk-through, docs, and the phone check

**Files:**
- Test: `tests/test_score_flow.py` (new)
- Modify: `README.md`: add a section "Enter scores" after "Event page and share link", covering who can score, Save anyway, forfeit, clear, and the lock on setup and regenerate once a score exists.
- Modify: `Pickleball League Manager — PRD, ERD & Scheduling Spec.md` §9: tick P8.

- [ ] **Step 1: Write the walk-through** `test_score_walkthrough` in `tests/test_score_flow.py`.
  - Run `call_command("seed_demo", "--tonight")`.
  - Set the league to `match_format="best_of_3"` and `player_score_entry=True`.
  - **Admin:** log in as `admin@example.com`. On the Tonight schedule, find the first card's score link.
    - HTMX check with 1–1 shows Game 3.
    - HTMX save of 11–7, 9–11, 11–5 returns the OOB card with chips and "Last edited by".
    - Setup is now locked: `league.has_scores()` is True, and regenerate on the Preview is refused.
  - **Player:** log in as `player@example.com`.
    - Find a week-2 card of their team that's unscored, with a score link.
    - A save of 11–10, 11–5 is blocked with the win-by-2 message.
    - A save of 11–9, 11–5 succeeds.
  - **Admin again:**
    - Edit that match. The player's next save is refused with "An admin has already scored this match."
    - Forfeit a third match, then clear it. It is unscored, and the card says "Enter score".
- [ ] **Step 2: Run it.** Expected: PASS, since the behavior was built in Tasks 1–4. Fix anything it exposes in the owning code.
- [ ] **Step 3: Update** the README and the PRD tick.
- [ ] **Step 4: Run the full suite.** Expected: all PASS.
- [ ] **Step 5: Browser check at 390×844.**
  - Run `seed_demo --reset --tonight`, and set the demo league to best of 3 with player entry on.
  - Run `runserver`, then with the Playwright tools:
    - open Tonight as the admin and tap "Enter score";
    - check the sheet fills the screen and `document.documentElement.scrollWidth <= window.innerWidth`;
    - check the inputs have `inputmode="numeric"`;
    - type 11 / 7, tab, 7 / 11, and check that Game 3 appears and focus stays in the next box;
    - finish with 11 / 5 and save. The sheet closes, and the card shows chips and "Last edited by".
  - Take screenshots and look at them. Record the results in the task report.
- [ ] **Step 6: Commit** `feat(league): score entry walk-through and docs`
