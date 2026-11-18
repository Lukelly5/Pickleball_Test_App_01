# Scheduler (pure Python) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and test the league/tournament scheduler from PRD Section 6 as a standalone Python package with a command-line runner, before any Django or UI work.

**Architecture:** A `scheduler` package of small pure functions over frozen dataclasses. Pass 1 (`pairings`) decides who plays whom each week by taking whole circle-method rotations; Pass 2 (`placement`) packs a night's games into rounds and courts. Fairness reporting, swap checking and the tournament fit check are separate modules that read a `Schedule`. A thin CLI prints schedules so inputs can be tried by hand.

**Tech Stack:** Python 3.13, standard library only, pytest 9.

**Spec:** `Pickleball League Manager — PRD, ERD & Scheduling Spec.md` (Section 6; Flow A errors and Flow C messages in Section 4).

## Global Constraints

- No Django imports and no third-party runtime dependencies anywhere in `scheduler/`.
- Deterministic: the same inputs always produce the same schedule. No `random`, no iteration over unordered sets when order affects output.
- Weeks, rounds and courts are numbered from 1.
- The scheduler's input is **games per team** per week, never total games.
- Never split a rotation across weeks.
- Tests assert properties (counts, clashes, rounds used), not exact pairings.
- User-facing message text is copied verbatim from the PRD where the PRD gives it.
- Run tests from the repo root with `python -m pytest`.

## Review Focus

1. **A player on two teams in the same flight.** Those two teams can never play each other, and placement would loop forever. Expected: `generate` raises `ScheduleError` naming the player and flight before scheduling. (Task 3)
2. **One court.** Expected: every game gets its own round, no crash, all hard rules hold. (Task 3)
3. **Tiny flights: 2 teams and 3 teams.** Expected: 2 teams gives one game per rotation, repeating; 3 teams gives one game and one bye per rotation, byes rotating. (Task 1)
4. **Zero games per team in a week, and flights with different numbers of weeks.** Expected: a zero week produces no games for that flight and no crash; mismatched week counts raise `ScheduleError`. (Tasks 2 and 3)
5. **Bad CLI input** (1 team, 0 courts, non-numeric values). Expected: a one-line message on stderr and exit code 2, never a traceback. (Task 7)

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Project name, Python floor, pytest config |
| `scheduler/__init__.py` | Re-exports the public names |
| `scheduler/types.py` | `Team`, `Flight`, `Match`, `Schedule`, `ScheduleError` |
| `scheduler/pairings.py` | Pass 1: rotations, weekly slicing, once/twice preset |
| `scheduler/placement.py` | Pass 2: one night's games into rounds and courts |
| `scheduler/generate.py` | Input validation; runs Pass 1 then Pass 2 for every week |
| `scheduler/fairness.py` | Games per team, pair counts, longest sit |
| `scheduler/swap.py` | Swap games or teams, with clash checking |
| `scheduler/fit.py` | Tournament fit check and its messages |
| `scheduler/cli.py`, `scheduler/__main__.py` | `python -m scheduler …` |
| `tests/test_*.py` | One test file per module; `tests/helpers.py` builds flights |

---

### Task 1: Types and round-robin rotations

**Files:**
- Create: `pyproject.toml`, `scheduler/__init__.py`, `scheduler/types.py`, `scheduler/pairings.py`
- Test: `tests/__init__.py`, `tests/helpers.py`, `tests/test_rotations.py`

**Interfaces:**
- Produces, in `scheduler/types.py` (all dataclasses `frozen=True`):
  - `Team(id: str, name: str, players: tuple[str, str])`
  - `Flight(id: str, name: str, teams: tuple[Team, ...], games_per_team_by_week: tuple[int, ...])`
  - `Match(flight_id: str, week: int, round_no: int, court_no: int, team_a: Team, team_b: Team)`
  - `Schedule(matches: tuple[Match, ...], courts: int)` with method `week(self, n: int) -> tuple[Match, ...]`; `matches` is always sorted by `(week, round_no, court_no)`
  - `class ScheduleError(ValueError)`
- Produces, in `scheduler/pairings.py`:
  - `Pairing = tuple[Team, Team]`
  - `rotations(teams: Sequence[Team]) -> list[list[Pairing]]`
- Produces, in `tests/helpers.py`:
  - `make_teams(n: int, prefix: str = "T") -> tuple[Team, ...]` — ids `T1…Tn`, names `Team T1…`, players `("T1-a", "T1-b")`
  - `make_flight(n: int, games: Sequence[int], id: str = "F1", prefix: str = "T") -> Flight`

- [ ] **Step 1: Commit the revised PRD** so the spec this plan argues from is in history.

```bash
git add -- "Pickleball League Manager — PRD, ERD & Scheduling Spec.md"
git commit -m "Revise PRD: games-per-team scheduler, after-publish hooks, rebuilt ERD"
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "pickleball-league-manager"
version = "0.1.0"
requires-python = ">=3.13"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write `tests/helpers.py`** with `make_teams` and `make_flight` as specified in Interfaces, and an empty `tests/__init__.py`.

- [ ] **Step 4: Write the failing tests in `tests/test_rotations.py`**

```python
from collections import Counter
import pytest
from scheduler.pairings import rotations
from tests.helpers import make_teams

def pair(p): return frozenset(t.id for t in p)

@pytest.mark.parametrize("n", range(2, 13))
def test_full_cycle_is_a_round_robin(n):
    rots = rotations(make_teams(n))
    assert len(rots) == (n - 1 if n % 2 == 0 else n)
    all_pairs = Counter(pair(p) for r in rots for p in r)
    assert len(all_pairs) == n * (n - 1) // 2
    assert set(all_pairs.values()) == {1}

@pytest.mark.parametrize("n", range(2, 13))
def test_each_rotation_uses_each_team_at_most_once(n):
    for r in rotations(make_teams(n)):
        ids = [t.id for p in r for t in p]
        assert len(ids) == len(set(ids))
        assert len(r) == n // 2

@pytest.mark.parametrize("n", [3, 5, 7, 9, 11])
def test_odd_counts_give_each_team_exactly_one_bye_per_cycle(n):
    teams = make_teams(n)
    byes = []
    for r in rotations(teams):
        playing = {t.id for p in r for t in p}
        byes += [t.id for t in teams if t.id not in playing]
    assert sorted(byes) == sorted(t.id for t in teams)

def test_two_teams_is_one_rotation_of_one_game():
    assert [len(r) for r in rotations(make_teams(2))] == [1]

def test_same_input_same_output():
    assert rotations(make_teams(7)) == rotations(make_teams(7))
```

- [ ] **Step 5: Run to verify failure**

Run: `python -m pytest tests/test_rotations.py -q`
Expected: collection error, `No module named 'scheduler'`.

- [ ] **Step 6: Implement `scheduler/types.py`** per Interfaces. `Schedule.__post_init__` sorts `matches` (use `object.__setattr__`).

- [ ] **Step 7: Implement `rotations` in `scheduler/pairings.py`** using the circle method:

```python
seats = list(teams) + ([None] if len(teams) % 2 else [])
n = len(seats)
for _ in range(n - 1):
    # pair seat i with seat n-1-i; drop the pair containing None (the bye)
    # then keep seats[0] fixed and rotate the rest one place:
    seats = [seats[0], seats[-1], *seats[1:-1]]
```

- [ ] **Step 8: Run to verify pass**

Run: `python -m pytest tests/test_rotations.py -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml scheduler tests
git commit -m "feat(scheduler): types and circle-method rotations"
```

---

### Task 2: Weekly slicing and the once/twice preset

**Files:**
- Modify: `scheduler/pairings.py`
- Test: `tests/test_weekly.py`

**Interfaces:**
- Consumes: `rotations`, `Pairing`, `Flight`, `ScheduleError`, `make_flight`
- Produces:
  - `weekly_rotations(flight: Flight) -> list[list[list[Pairing]]]` — index `[week-1][k]` is the k-th rotation played that week
  - `round_robin_preset(n_teams: int, weeks: int, times: int) -> tuple[int, ...]`

- [ ] **Step 1: Write the failing tests in `tests/test_weekly.py`**

```python
from collections import Counter
import pytest
from scheduler.pairings import weekly_rotations, round_robin_preset
from scheduler.types import ScheduleError
from tests.helpers import make_flight

def games_per_team(week):  # week = list of rotations
    return Counter(t.id for rot in week for p in rot for t in p)

# PRD T7
@pytest.mark.parametrize("n", range(4, 13))
@pytest.mark.parametrize("g", [1, 2, 3])
def test_T7_nobody_gets_an_empty_night(n, g):
    flight = make_flight(n, [g] * 4)
    for week in weekly_rotations(flight):
        counts = games_per_team(week)
        per_team = [counts.get(t.id, 0) for t in flight.teams]
        if n % 2 == 0:
            assert set(per_team) == {g}
        else:
            assert set(per_team) <= {g, g - 1}
            if g >= 2:
                assert min(per_team) >= 1

# PRD T9
def test_T9_rotating_bye():
    flight = make_flight(5, [1] * 5)
    weeks = weekly_rotations(flight)
    sat_out = []
    for week in weeks:
        assert sum(len(r) for r in week) == 2
        playing = set(games_per_team(week))
        sat_out += [t.id for t in flight.teams if t.id not in playing]
    assert sorted(sat_out) == sorted(t.id for t in flight.teams)
    pairs = Counter(frozenset(t.id for t in p) for w in weeks for r in w for p in r)
    assert len(pairs) == 10 and set(pairs.values()) == {1}

@pytest.mark.parametrize("n,games", [(4, [2, 2, 2, 2]), (6, [3, 1, 2, 3]), (5, [2, 2, 2])])
def test_every_pair_meets_k_times_before_any_meets_k_plus_1(n, games):
    flight = make_flight(n, games)
    pairs = Counter()
    for week in weekly_rotations(flight):
        for rot in week:
            pairs.update(frozenset(t.id for t in p) for p in rot)
            total_pairs = n * (n - 1) // 2
            values = list(pairs.values()) + [0] * (total_pairs - len(pairs))
            # only checked at cycle granularity: spread never exceeds 1
            assert max(values) - min(values) <= 1

def test_zero_games_week_is_empty_and_does_not_advance():
    a = weekly_rotations(make_flight(4, [1, 0, 1]))
    b = weekly_rotations(make_flight(4, [1, 1]))
    assert a[1] == [] and a[2] == b[1]

def test_preset_values():
    assert round_robin_preset(4, 3, 1) == (1, 1, 1)
    assert round_robin_preset(6, 4, 1) == (2, 1, 1, 1)
    assert round_robin_preset(4, 4, 2) == (2, 2, 1, 1)
    assert round_robin_preset(5, 5, 1) == (1, 1, 1, 1, 1)

def test_preset_blocks_an_empty_week():
    with pytest.raises(ScheduleError) as e:
        round_robin_preset(4, 4, 1)
    assert str(e.value) == (
        "Round robin once is 3 games per team, but you have 4 weeks. "
        "Week 4 has no games — reduce weeks or choose twice."
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_weekly.py -q`
Expected: `ImportError: cannot import name 'weekly_rotations'`.

- [ ] **Step 3: Implement `weekly_rotations`.** Keep one position counter across weeks; week `w` takes the next `g` rotations from the cycle, wrapping with modulo.

- [ ] **Step 4: Implement `round_robin_preset`.** Total rotations = `times × (n−1 if n even else n)`; split as evenly as possible with earlier weeks taking the remainder. If total < weeks, raise `ScheduleError` with the message in the test, where the number is the total rotations, the week is the first empty one, and "once"/"twice" follows `times` (for `times == 2` the tail reads "reduce weeks or choose custom.").

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest tests/test_weekly.py tests/test_rotations.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scheduler tests
git commit -m "feat(scheduler): whole-rotation weekly slicing and round-robin preset"
```

---

### Task 3: Placement into rounds and courts, and `generate`

**Files:**
- Create: `scheduler/placement.py`, `scheduler/generate.py`
- Modify: `scheduler/__init__.py` (export `generate`, `Team`, `Flight`, `Match`, `Schedule`, `ScheduleError`)
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `weekly_rotations`, types, helpers
- Produces:
  - `place_night(week: int, flights: Sequence[tuple[str, list[list[Pairing]]]], courts: int) -> list[Match]` — each tuple is `(flight_id, that week's rotations)`, in flight input order
  - `generate(flights: Sequence[Flight], courts: int) -> Schedule`

- [ ] **Step 1: Write the failing tests in `tests/test_generate.py`**

```python
from collections import Counter, defaultdict
import pytest
from scheduler import generate, Flight, Team, ScheduleError
from tests.helpers import make_flight, make_teams

def assert_hard_rules(s):
    slots = Counter((m.week, m.round_no, m.court_no) for m in s.matches)
    assert set(slots.values()) <= {1}                      # one game per court per round
    assert all(1 <= m.court_no <= s.courts for m in s.matches)
    busy = defaultdict(list)
    for m in s.matches:
        busy[(m.week, m.round_no)] += [*m.team_a.players, *m.team_b.players]
    for players in busy.values():
        assert len(players) == len(set(players))           # no player twice in a round

def per_team(matches):
    return Counter(t.id for m in matches for t in (m.team_a, m.team_b))

def pair_counts(matches):
    return Counter(frozenset((m.team_a.id, m.team_b.id)) for m in matches)

def test_T1_swish_example():
    s = generate([make_flight(4, [2, 2, 2, 2])], courts=2)
    assert_hard_rules(s)
    assert len(s.matches) == 16
    for w in range(1, 5):
        wk = s.week(w)
        assert {(m.round_no, m.court_no) for m in wk} == {(1, 1), (1, 2), (2, 1), (2, 2)}
        assert set(per_team(wk).values()) == {2}
    assert set(per_team(s.matches).values()) == {8}
    assert sorted(pair_counts(s.matches).values()) == [2, 2, 3, 3, 3, 3]

def test_T2_different_numbers_week_to_week():
    s = generate([make_flight(10, [1, 2])], courts=5)
    assert_hard_rules(s)
    assert len(s.week(1)) == 5 and max(m.round_no for m in s.week(1)) == 1
    assert len(s.week(2)) == 10 and max(m.round_no for m in s.week(2)) == 2
    assert set(per_team(s.week(1)).values()) == {1}
    assert set(per_team(s.week(2)).values()) == {2}
    assert set(pair_counts(s.matches).values()) == {1}

def test_T4_odd_teams():
    s = generate([make_flight(5, [5])], courts=2)
    assert_hard_rules(s)
    assert len(s.matches) == 10
    assert max(m.round_no for m in s.matches) == 5
    assert set(per_team(s.matches).values()) == {4}
    assert set(pair_counts(s.matches).values()) == {1}

def test_T5_player_in_two_flights():
    mens = list(make_teams(4, "M")); mixed = list(make_teams(4, "X"))
    mens[0] = Team("M1", "Team M1", ("pat", "M1-b"))
    mixed[0] = Team("X1", "Team X1", ("pat", "X1-b"))
    s = generate([Flight("men", "Int Men's", tuple(mens), (1,)),
                  Flight("mix", "Int Mixed", tuple(mixed), (1,))], courts=4)
    assert_hard_rules(s)
    pats = [m.round_no for m in s.matches if "pat" in m.team_a.players + m.team_b.players]
    assert sorted(pats) == [1, 2]
    assert max(m.round_no for m in s.matches) == 2

def test_T8_short_sits():
    s = generate([make_flight(6, [2])], courts=2)
    assert_hard_rules(s)
    assert max(m.round_no for m in s.matches) == 3
    rounds = defaultdict(list)
    for m in s.matches:
        rounds[m.team_a.id].append(m.round_no); rounds[m.team_b.id].append(m.round_no)
    assert all(max(r) - min(r) - 1 <= 1 for r in rounds.values())

def test_flights_are_interleaved():
    s = generate([make_flight(4, [1], "A", "A"), make_flight(4, [1], "B", "B")], courts=2)
    assert {m.flight_id for m in s.matches if m.round_no == 1} == {"A", "B"}

@pytest.mark.parametrize("n", range(2, 13))
@pytest.mark.parametrize("courts", [1, 2, 3, 5])
def test_hard_rules_hold_everywhere(n, courts):
    s = generate([make_flight(n, [2, 1, 3])], courts=courts)
    assert_hard_rules(s)

def test_one_court_gives_every_game_its_own_round():
    s = generate([make_flight(4, [2])], courts=1)
    assert sorted(m.round_no for m in s.matches) == [1, 2, 3, 4]

def test_same_inputs_same_schedule():
    args = ([make_flight(7, [2, 3, 1])], 3)
    assert generate(*args) == generate(*args)

def test_too_few_teams():
    with pytest.raises(ScheduleError) as e:
        generate([Flight("f", "Intermediate Mixed", make_teams(1), (1,))], courts=2)
    assert str(e.value) == "Add at least 2 teams to Intermediate Mixed before generating."

def test_player_on_two_teams_in_one_flight():
    teams = (Team("a", "A", ("pat", "x")), Team("b", "B", ("pat", "y")))
    with pytest.raises(ScheduleError) as e:
        generate([Flight("f", "Int Men's", teams, (1,))], courts=2)
    assert str(e.value) == "pat is on two teams in Int Men's."

@pytest.mark.parametrize("flights,courts", [
    ([make_flight(4, [1])], 0),                                   # no courts
    ([make_flight(4, [-1])], 2),                                  # negative games
    ([make_flight(4, [1, 1], "A", "A"), make_flight(4, [1], "B", "B")], 2),  # week counts differ
    ([make_flight(4, [1]), make_flight(4, [1])], 2),              # duplicate flight / team ids
])
def test_invalid_inputs_raise(flights, courts):
    with pytest.raises(ScheduleError):
        generate(flights, courts)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_generate.py -q`
Expected: `ImportError: cannot import name 'generate'`.

- [ ] **Step 3: Implement `place_night` in `scheduler/placement.py`.** The ordering is the part the tests don't fully pin:

```python
# for k in 0 .. (most rotations any flight has this week) - 1:
#   games = k-th rotation of every flight, interleaved:
#           flight1 game1, flight2 game1, flight1 game2, flight2 game2, ...
#   stable-sort games by max(last_round[team_a], last_round[team_b])   # 0 if not played tonight
#   for each game: place in the lowest round r >= 1 where
#       courts used in r < courts  and  none of its 4 players is busy in r;
#       court_no = lowest free court in r; update last_round for both teams
```

- [ ] **Step 4: Implement `generate` in `scheduler/generate.py`.** Validate first, raising `ScheduleError`: fewer than 2 teams (message in test, uses flight name); a player id appearing on two teams of one flight (message in test); a team listing the same player twice; `courts < 1`; any negative games value; flights with different numbers of weeks; duplicate flight ids or duplicate team ids across the event. Then for each week call `place_night` with every flight's rotations for that week and return a `Schedule`.

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scheduler tests
git commit -m "feat(scheduler): round and court placement, generate with validation"
```

---

### Task 4: Fairness report

**Files:**
- Create: `scheduler/fairness.py`
- Modify: `scheduler/__init__.py` (export `fairness_report`)
- Test: `tests/test_fairness.py`

**Interfaces:**
- Consumes: `Schedule`, `Flight`, `generate`
- Produces:
  - `FairnessReport` (frozen dataclass) with fields
    - `games_by_week: dict[int, dict[str, int]]` — week → team id → games (teams with 0 included)
    - `games_total: dict[str, int]`
    - `pair_counts: dict[frozenset[str], int]` — every possible pair within a flight, 0 included
    - `longest_sit: dict[int, dict[str, int]]` — week → team id → most rounds idle between two of its consecutive games that night (0 if it plays fewer than 2)
  - `fairness_report(schedule: Schedule, flights: Sequence[Flight]) -> FairnessReport`

- [ ] **Step 1: Write the failing tests in `tests/test_fairness.py`**

```python
from scheduler import generate, fairness_report
from tests.helpers import make_flight

def test_T1_numbers():
    f = make_flight(4, [2, 2, 2, 2])
    r = fairness_report(generate([f], 2), [f])
    assert all(set(r.games_by_week[w].values()) == {2} for w in range(1, 5))
    assert set(r.games_total.values()) == {8}
    assert sorted(r.pair_counts.values()) == [2, 2, 3, 3, 3, 3]
    assert all(v == 0 for wk in r.longest_sit.values() for v in wk.values())

def test_bye_team_shows_zero_not_missing():
    f = make_flight(5, [1])
    r = fairness_report(generate([f], 2), [f])
    assert sorted(r.games_by_week[1].values()) == [0, 1, 1, 1, 1]

def test_unmet_pairs_show_zero():
    f = make_flight(6, [1])
    r = fairness_report(generate([f], 3), [f])
    assert len(r.pair_counts) == 15 and sorted(r.pair_counts.values()).count(0) == 12

def test_longest_sit_counts_idle_rounds():
    f = make_flight(6, [2])
    r = fairness_report(generate([f], 2), [f])
    assert max(r.longest_sit[1].values()) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_fairness.py -q`
Expected: `ImportError: cannot import name 'fairness_report'`.

- [ ] **Step 3: Implement `fairness_report`.** Pairs are only formed within a flight.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scheduler tests
git commit -m "feat(scheduler): fairness report"
```

---

### Task 5: Swaps with clash checking

**Files:**
- Create: `scheduler/swap.py`
- Modify: `scheduler/__init__.py` (export `swap_games`, `swap_teams`, `SwapConflict`)
- Test: `tests/test_swap.py`

**Interfaces:**
- Consumes: `Schedule`, `Match`, `ScheduleError`, `generate`
- Produces:
  - `Slot = tuple[int, int, int]` — `(week, round_no, court_no)`
  - `class SwapConflict(ScheduleError)`
  - `swap_games(schedule: Schedule, a: Slot, b: Slot) -> Schedule` — the two matches trade round and court
  - `swap_teams(schedule: Schedule, a: tuple[Slot, str], b: tuple[Slot, str]) -> Schedule` — the string is `"a"` or `"b"` (which side of that match); the two teams trade places
  - Both return a new `Schedule` and never modify the input. Both raise `SwapConflict` if the result breaks a hard rule, and `KeyError` if a slot has no match.

- [ ] **Step 1: Write the failing tests in `tests/test_swap.py`**

```python
import re
import pytest
from scheduler import generate, swap_games, swap_teams, SwapConflict
from tests.helpers import make_flight

def t1(): return generate([make_flight(4, [2, 2, 2, 2])], courts=2)

def test_T6_swap_across_rounds_is_blocked():
    s = t1()
    with pytest.raises(SwapConflict) as e:
        swap_games(s, (1, 1, 1), (1, 2, 2))
    assert re.fullmatch(
        r"Can't swap: Team T\d would play on Court \d and Court \d in Round \d\.", str(e.value))

def test_swap_within_a_round_trades_courts():
    s = t1()
    before = {m.court_no: (m.team_a.id, m.team_b.id) for m in s.week(1) if m.round_no == 1}
    after_s = swap_games(s, (1, 1, 1), (1, 1, 2))
    after = {m.court_no: (m.team_a.id, m.team_b.id) for m in after_s.week(1) if m.round_no == 1}
    assert after == {1: before[2], 2: before[1]}
    assert s == t1()                                   # input untouched

def test_swap_teams_within_a_round_is_allowed():
    s = swap_teams(t1(), ((1, 1, 1), "a"), ((1, 1, 2), "a"))
    ids = [t.id for m in s.week(1) if m.round_no == 1 for t in (m.team_a, m.team_b)]
    assert sorted(ids) == ["T1", "T2", "T3", "T4"]

def test_swap_teams_across_rounds_is_blocked():
    with pytest.raises(SwapConflict):
        swap_teams(t1(), ((1, 1, 1), "a"), ((1, 2, 1), "a"))

def test_swap_teams_across_flights_is_blocked():
    s = generate([make_flight(4, [1], "A", "A"), make_flight(4, [1], "B", "B")], courts=4)
    a = next(m for m in s.matches if m.flight_id == "A")
    b = next(m for m in s.matches if m.flight_id == "B")
    with pytest.raises(SwapConflict) as e:
        swap_teams(s, ((a.week, a.round_no, a.court_no), "a"), ((b.week, b.round_no, b.court_no), "a"))
    assert str(e.value) == "Can't swap: teams can only play teams in their own flight."

def test_swap_across_weeks_is_blocked():
    with pytest.raises(SwapConflict) as e:
        swap_games(t1(), (1, 1, 1), (2, 1, 1))
    assert str(e.value) == "Can't swap: games must be in the same week."

def test_missing_slot():
    with pytest.raises(KeyError):
        swap_games(t1(), (1, 9, 9), (1, 1, 1))
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_swap.py -q`
Expected: `ImportError: cannot import name 'swap_games'`.

- [ ] **Step 3: Implement `scheduler/swap.py`.** Build the candidate schedule, then check every round of the affected week. Clash message: `"Can't swap: {who} would play on Court {x} and Court {y} in Round {r}."` with `x < y`; `{who}` is the team's `name` when the same team appears twice, otherwise the player id. A team swapped into a match against itself reports the same-team clash for that court pair (`x == y` is allowed in that one case). `swap_teams` also applies the same-week and same-flight rules, with the messages in the tests.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scheduler tests
git commit -m "feat(scheduler): game and team swaps with clash checks"
```

---

### Task 6: Tournament fit check

**Files:**
- Create: `scheduler/fit.py`
- Modify: `scheduler/__init__.py` (export `check_fit`, `fit_message`, `FitResult`)
- Test: `tests/test_fit.py`

**Interfaces:**
- Consumes: `generate`, `Flight`
- Produces:
  - `FitResult` (frozen dataclass): `games: int`, `rounds: int`, `courts: int`, `minutes: int`, `window_minutes: int`, `fits: bool`, `rounds_that_fit: int`, `suggested_games_per_team: int | None`
  - `check_fit(flights: Sequence[Flight], courts: int, game_minutes: int, window_minutes: int) -> FitResult` — each flight must have exactly one week
  - `fit_message(result: FitResult) -> str`

- [ ] **Step 1: Write the failing tests in `tests/test_fit.py`**

```python
import pytest
from scheduler import check_fit, fit_message, ScheduleError
from tests.helpers import make_flight

def test_T3_does_not_fit():
    r = check_fit([make_flight(8, [7])], courts=4, game_minutes=15, window_minutes=60)
    assert (r.games, r.rounds, r.minutes, r.fits) == (28, 7, 105, False)
    assert (r.rounds_that_fit, r.suggested_games_per_team) == (4, 4)
    assert fit_message(r) == (
        "28 games need 7 rounds on 4 courts (~1h 45m). Your 60-minute window fits 4 rounds. "
        "Add courts, extend the window, or lower games per team to 4.")

def test_T3_fits_at_four_games_per_team():
    r = check_fit([make_flight(8, [4])], courts=4, game_minutes=15, window_minutes=60)
    assert (r.games, r.rounds, r.fits, r.suggested_games_per_team) == (16, 4, True, None)

def test_fits_message():
    r = check_fit([make_flight(8, [7])], courts=4, game_minutes=15, window_minutes=120)
    assert fit_message(r) == (
        "28 games · 7 rounds on 4 courts · about 1h 45m. Fits your 2-hour window.")

def test_nothing_fits():
    r = check_fit([make_flight(8, [7])], courts=1, game_minutes=15, window_minutes=30)
    assert r.fits is False and r.suggested_games_per_team is None
    assert fit_message(r).endswith("Add courts or extend the window.")

def test_leagues_are_rejected():
    with pytest.raises(ScheduleError):
        check_fit([make_flight(4, [1, 1])], 2, 15, 60)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_fit.py -q`
Expected: `ImportError: cannot import name 'check_fit'`.

- [ ] **Step 3: Implement `check_fit`.** `rounds` comes from actually running `generate`. `rounds_that_fit = window_minutes // game_minutes`. For the suggestion, try caps `c` from (largest current games-per-team − 1) down to 1, regenerating with each flight at `min(its value, c)`; the first cap that fits is the suggestion, else `None`.

- [ ] **Step 4: Implement `fit_message`.** Durations: `105 → "1h 45m"`, `120 → "2h"`, `45 → "45m"`. Window: whole hours above 60 minutes read `"2-hour"`, everything else `"60-minute"`. When `suggested_games_per_team is None` the last sentence is `"Add courts or extend the window."`.

- [ ] **Step 5: Run to verify pass**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scheduler tests
git commit -m "feat(scheduler): tournament fit check"
```

---

### Task 7: Command-line runner

**Files:**
- Create: `scheduler/cli.py`, `scheduler/__main__.py`, `examples/two_flights.json`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `generate`, `fairness_report`, `check_fit`, `fit_message`, `round_robin_preset`, `ScheduleError`
- Produces: `main(argv: Sequence[str] | None = None) -> int`; `scheduler/__main__.py` calls `sys.exit(main())`

Commands:

```
python -m scheduler league --teams 4 --weeks 4 --games-per-team 2 --courts 2
python -m scheduler league --teams 10 --weeks 2 --games-per-team 1,2 --courts 5
python -m scheduler league --teams 4,6 --weeks 4 --preset twice --courts 3
python -m scheduler league --file examples/two_flights.json
python -m scheduler tournament --teams 8 --courts 4 --game-minutes 15 --window 60 [--games-per-team 4]
```

- `--teams` takes one count per flight, comma-separated; flights are named `Flight 1…`, teams `F1-T1…`.
- `--games-per-team` takes one number (used every week) or one per week; `--preset once|twice` replaces it. Exactly one of the two is required for `league`. For `tournament` it defaults to a full round robin.
- `--file` JSON shape: `{"courts": 4, "flights": [{"name": "Int Men's", "games_per_team": [1, 1], "teams": [{"name": "Dinkers", "players": ["Pat", "Sam"]}]}]}`. `examples/two_flights.json` has 4 courts and two 4-team flights, each with `"games_per_team": [1]`, sharing the player `"Pat"` (so all 4 games would fit in Round 1 if Pat weren't on two teams).

Output for each week, then a fairness block:

```
Week 1
          Court 1               Court 2
Round 1   F1-T1 v F1-T4         F1-T2 v F1-T3
Round 2   F1-T1 v F1-T3         F1-T4 v F1-T2
Per team: F1-T1 2 · F1-T2 2 · F1-T3 2 · F1-T4 2 · longest sit 0 rounds

Total: 16 games · 8 per team · every pair meets 2–3 times
```

The total line reads "N per team" when all teams are equal, otherwise "N–M per team"; likewise "meets N times" or "N–M times". With more than one flight, cells are prefixed with the flight name and there is one total line per flight. `tournament` prints the same grid followed by `fit_message`.

- [ ] **Step 1: Write the failing tests in `tests/test_cli.py`**

```python
import pytest
from scheduler.cli import main

def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err

def test_T1_from_the_command_line(capsys):
    code, out, _ = run(capsys, "league", "--teams", "4", "--weeks", "4",
                       "--games-per-team", "2", "--courts", "2")
    assert code == 0
    assert out.count("Week ") == 4 and "Round 2" in out and "Round 3" not in out
    assert "Total: 16 games · 8 per team · every pair meets 2–3 times" in out

def test_per_week_list_and_preset(capsys):
    code, out, _ = run(capsys, "league", "--teams", "10", "--weeks", "2",
                       "--games-per-team", "1,2", "--courts", "5")
    assert code == 0 and "Total: 15 games" in out
    code, out, _ = run(capsys, "league", "--teams", "4", "--weeks", "3",
                       "--preset", "once", "--courts", "2")
    assert code == 0 and "every pair meets 1 times" not in out and "meets once" in out

def test_tournament_prints_fit_message(capsys):
    code, out, _ = run(capsys, "tournament", "--teams", "8", "--courts", "4",
                       "--game-minutes", "15", "--window", "60")
    assert code == 0 and "lower games per team to 4." in out

def test_file_input_keeps_shared_player_apart(capsys):
    code, out, _ = run(capsys, "league", "--file", "examples/two_flights.json")
    assert code == 0 and "Round 2" in out

@pytest.mark.parametrize("argv", [
    ["league", "--teams", "1", "--weeks", "2", "--games-per-team", "1", "--courts", "2"],
    ["league", "--teams", "4", "--weeks", "2", "--games-per-team", "1", "--courts", "0"],
    ["league", "--teams", "4", "--weeks", "3", "--games-per-team", "1,2", "--courts", "2"],
    ["league", "--teams", "4", "--weeks", "4", "--preset", "once", "--courts", "2"],
    ["league", "--teams", "four", "--weeks", "2", "--games-per-team", "1", "--courts", "2"],
    ["league", "--file", "does-not-exist.json"],
])
def test_bad_input_is_a_message_not_a_traceback(capsys, argv):
    try:
        code = main(argv)
    except SystemExit as e:      # argparse exits by itself for unparseable values
        code = e.code
    err = capsys.readouterr().err
    assert code == 2 and err.strip() and "Traceback" not in err
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_cli.py -q`
Expected: `ModuleNotFoundError: No module named 'scheduler.cli'`.

- [ ] **Step 3: Implement `scheduler/cli.py` and `scheduler/__main__.py`** with `argparse` subcommands. Catch `ScheduleError`, `OSError` and `json.JSONDecodeError` in `main`, print `error: <message>` to stderr and return 2. A games-per-team list whose length isn't 1 or `--weeks` is a `ScheduleError`. In the total line, a pair count of exactly 1 reads "every pair meets once" and exactly 2 reads "every pair meets twice". Write `examples/two_flights.json`.

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Try it by hand**

Run: `python -m scheduler league --teams 4 --weeks 4 --games-per-team 2 --courts 2`
Expected: four week grids of 2 rounds × 2 courts and the line `Total: 16 games · 8 per team · every pair meets 2–3 times`.

- [ ] **Step 6: Commit**

```bash
git add scheduler tests examples
git commit -m "feat(scheduler): command-line runner"
```

---

## PRD test map

| PRD test | Where it lives |
| --- | --- |
| T1 | `test_generate.py::test_T1_swish_example`, `test_fairness.py::test_T1_numbers` |
| T2 | `test_generate.py::test_T2_different_numbers_week_to_week` |
| T3 | `test_fit.py::test_T3_*` |
| T4 | `test_generate.py::test_T4_odd_teams` |
| T5 | `test_generate.py::test_T5_player_in_two_flights` |
| T6 | `test_swap.py::test_T6_swap_across_rounds_is_blocked` |
| T7 | `test_weekly.py::test_T7_nobody_gets_an_empty_night` |
| T8 | `test_generate.py::test_T8_short_sits` |
| T9 | `test_weekly.py::test_T9_rotating_bye` |
| Same inputs, same schedule | `test_generate.py::test_same_inputs_same_schedule` |
