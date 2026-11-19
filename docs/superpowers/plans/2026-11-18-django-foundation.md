# Django Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Django project with every table from the PRD's ERD, a usable Django admin, a service that runs the existing `scheduler` package against database rows and saves the result as `Match` rows, and a demo seed command.

**Architecture:** One Django project (`config/`) with two apps: `accounts` (custom email-login `User` and `Organization`, which must exist in the first migration) and `league` (the other ten tables). `league/scheduling.py` is the only code that converts between ORM rows and the frozen dataclasses in `scheduler/`; `scheduler/` stays free of Django. No public pages yet. Auth flows, the wizard and the schedule screens come in later plans and build on these models.

**Tech Stack:** Python 3.13, Django 6.1, SQLite, pytest 9 + pytest-django 4.14.

**Spec:** `Pickleball League Manager — PRD, ERD & Scheduling Spec.md`: Section 7 (ERD, data flow, design choices), Section 2 (roles), Section 8 build checklist items 1 and last ("Models and migrations…", "Seed script…"). The scheduler plan `docs/superpowers/plans/2026-11-18-scheduler.md` describes the package this plan calls.

## Global Constraints

- Run all Python through the repo's venv: `.venv/Scripts/python` (Windows). Tests: `.venv/Scripts/python -m pytest` from the repo root.
- `scheduler/` gets no Django imports and no edits in this plan. The existing scheduler tests must keep passing.
- Custom user model `accounts.User` is set in `AUTH_USER_MODEL` before the first `migrate`. Users log in with email; there is no username field.
- Every top-level record hangs off an `Organization` (`Event`, `Player`, `User`).
- Standings are never stored (PRD §7). There is no standings table or cached column.
- Choice values are lower-case strings stored in the database: event type `league`/`tournament`; event status `draft`/`published`/`completed`; week status `scheduled`/`cancelled`; match status `scheduled`/`final`/`cancelled`/`void`; invite role `admin`/`player`.
- Scoring defaults (A3): match format single game, points to win 11, win by 2 on, player score entry off. Tournament game length default 15 minutes (A2).
- `TIME_ZONE = "America/Chicago"` (Waco), `USE_TZ = True`. The PRD lists time zone as not yet decided, so this is a default to confirm.
- Email uses the console backend (PRD risk: no real email in the class demo).
- Error text shown to the Director is written in plain English and names the flight or team.

## Review Focus

1. **One person on a Men's and a Mixed team in the same division (T5 through the database).** Their two games must never share a round. Players are identified by `Player` row, not by name, so two different people named "Pat Lee" are not treated as one person. (Task 4)
2. **Regenerating an event that already has matches.** Old `Match` rows are replaced, not added to. Regenerating is blocked once any match is final or has scores (A13), and allowed otherwise, including after publish. (Task 4)
3. **A team with 1 or 3 players.** The database can't stop this, so generation fails with "Dinkers needs exactly 2 players before generating." instead of crashing. (Task 4)
4. **A flight's games-per-team list doesn't match the event's number of weeks**, or the event has no flights. Generation stops with a message naming the flight. (Task 4)
5. **`seed_demo` run twice.** No duplicates and no crash. The second run reports that demo data exists; `--reset` rebuilds it. (Task 5)

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml` | Adds Django runtime dependency, pytest-django, `DJANGO_SETTINGS_MODULE` |
| `.gitignore` | Adds `db.sqlite3` |
| `manage.py`, `config/{__init__,settings,urls,wsgi,asgi}.py` | Django project |
| `accounts/models.py`, `accounts/admin.py`, `accounts/apps.py` | `Organization`, `User`, `UserManager` |
| `league/models.py` | Player, Invite, Event, Division, Flight, Team, TeamMember, Week, Match, GameScore |
| `league/admin.py` | Admin registrations, inlines, "Generate schedule" action |
| `league/scheduling.py` | ORM ↔ `scheduler` conversion, `generate_event`, `load_schedule` |
| `league/management/commands/seed_demo.py` | Demo data |
| `tests/factories.py` | Plain functions that build database rows for tests |
| `tests/test_accounts.py`, `tests/test_league_models.py`, `tests/test_admin.py`, `tests/test_scheduling_bridge.py`, `tests/test_seed.py` | One test file per area |
| `README.md` | How to install, migrate, seed, run and test |

---

### Task 1: Django project, accounts app, custom user

**Files:**
- Modify: `pyproject.toml`, `.gitignore`
- Create: `manage.py`, `config/*`, `accounts/__init__.py`, `accounts/apps.py`, `accounts/models.py`, `accounts/admin.py`, `accounts/migrations/0001_initial.py` (generated), `league/__init__.py`, `league/apps.py`, `league/models.py` (empty for now), `README.md`
- Test: `tests/test_accounts.py`

**Interfaces:**
- Produces, in `accounts/models.py`:
  - `Organization(name: CharField(max_length=200, unique=True))`, `__str__` → name
  - `UserManager(BaseUserManager)` with `create_user(email: str, password: str | None = None, **extra) -> User` and `create_superuser(email: str, password: str, **extra) -> User`
  - `User(AbstractUser)`: `username = None`; `email = EmailField(unique=True)`; `organization = ForeignKey(Organization, null=True, blank=True, on_delete=SET_NULL, related_name="users")`; `is_admin = BooleanField(default=False)` (the league Admin role from PRD §2, separate from `is_staff`, which is Django-admin access); `USERNAME_FIELD = "email"`; `REQUIRED_FIELDS = []`; `objects = UserManager()`
- Produces settings: `AUTH_USER_MODEL = "accounts.User"`, `INSTALLED_APPS` includes `"accounts"` and `"league"`.

- [ ] **Step 1: Install dependencies and record them**

```powershell
.venv/Scripts/python -m pip install "django>=6.1,<6.2" "pytest-django>=4.14"
```

In `pyproject.toml`: add `dependencies = ["django>=6.1,<6.2"]` under `[project]`; set `dev = ["pytest>=9", "pytest-django>=4.14"]`; add `DJANGO_SETTINGS_MODULE = "config.settings"` under `[tool.pytest.ini_options]`. Add `db.sqlite3` to `.gitignore`.

- [ ] **Step 2: Scaffold**

```powershell
.venv/Scripts/django-admin startproject config .
.venv/Scripts/python manage.py startapp accounts
.venv/Scripts/python manage.py startapp league
```

Delete the generated `tests.py` and `views.py` in both apps (tests live in `tests/`). Do **not** run `migrate` yet.

- [ ] **Step 3: Settings.** In `config/settings.py`:
  - `SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")`
  - `DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"`
  - `ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")`
  - Add `"accounts"`, `"league"` to `INSTALLED_APPS`; `AUTH_USER_MODEL = "accounts.User"`
  - `TIME_ZONE = "America/Chicago"`, `USE_TZ = True`
  - `EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"`
  - `TEMPLATES[0]["DIRS"] = [BASE_DIR / "templates"]`
  - `config/urls.py` keeps only `path("admin/", admin.site.urls)`; set `admin.site.site_header = "Pickleball League Manager"`.

- [ ] **Step 4: Write the failing tests** in `tests/test_accounts.py` (`pytestmark = pytest.mark.django_db`):

```python
def test_create_user_logs_in_by_email():
    user = User.objects.create_user("Pat@Example.com", "pw12345!")
    assert user.email == "Pat@example.com"          # domain normalised
    assert user.check_password("pw12345!")
    assert not user.is_admin and not user.is_staff
    assert not hasattr(user, "username") or user.username is None

def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user("", "pw")

def test_create_superuser_is_staff_superuser_and_league_admin():
    user = User.objects.create_superuser("admin@example.com", "pw12345!")
    assert user.is_staff and user.is_superuser and user.is_admin

def test_email_is_unique():
    User.objects.create_user("a@example.com", "pw")
    with pytest.raises(IntegrityError):
        User.objects.create_user("a@example.com", "pw")

def test_user_belongs_to_organization():
    org = Organization.objects.create(name="Waco Regional")
    user = User.objects.create_user("a@example.com", "pw", organization=org)
    assert list(org.users.all()) == [user]

def test_admin_login_page_loads(client):
    assert client.get("/admin/login/").status_code == 200
```

- [ ] **Step 5: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_accounts.py -v`
Expected: FAIL / errors (`User` has no `create_user` with email, or import errors).

- [ ] **Step 6: Implement `Organization`, `UserManager`, `User`** as in the Interfaces block. `create_superuser` sets `is_staff`, `is_superuser` and `is_admin` to `True`. Register both in `accounts/admin.py`: `User` with a `UserAdmin` subclass whose `ordering`, `list_display` (`email`, `organization`, `is_admin`, `is_staff`), `fieldsets` and `add_fieldsets` use `email` instead of `username`.

- [ ] **Step 7: Generate the migration and verify**

```powershell
.venv/Scripts/python manage.py makemigrations accounts
.venv/Scripts/python manage.py check
.venv/Scripts/python -m pytest -v
```

Expected: `check` reports no issues; all accounts tests and every existing scheduler test pass.

- [ ] **Step 8: README.** Short sections: Setup (create `.venv`, then the install line from Step 1), `manage.py migrate`, `manage.py createsuperuser`, `manage.py seed_demo` (added in Task 5), `manage.py runserver`, `python -m pytest`, `python -m scheduler --help`.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitignore manage.py config accounts league README.md tests/test_accounts.py
git commit -m "feat(django): project scaffold with email-login custom user and organization"
```

---

### Task 2: League models and migrations

**Files:**
- Modify: `league/models.py`
- Create: `league/migrations/0001_initial.py` (generated), `tests/factories.py`
- Test: `tests/test_league_models.py`

**Interfaces:**
- Consumes: `accounts.Organization`, `settings.AUTH_USER_MODEL`.
- Produces, in `league/models.py` (each choices class nested on its model as `TextChoices`/`IntegerChoices`):
  - `Player(organization FK CASCADE related_name="players", name CharField(120), email EmailField(blank=True), user OneToOneField(User, null, blank, SET_NULL, related_name="player"))`. Constraint: unique `(organization, email)` when `email != ""` (conditional `UniqueConstraint`, name `unique_player_email_per_org`).
  - `Invite(organization FK CASCADE, email EmailField, token CharField(64, unique, default=new_token), role Role{ADMIN="admin", PLAYER="player"}, player FK Player null blank CASCADE, created_by FK User null blank SET_NULL, created_at auto_now_add, expires_at DateTimeField(default=invite_expiry), accepted_at DateTimeField null blank)`. Method `is_expired(self, now: datetime | None = None) -> bool`.
  - Module functions `new_token() -> str` = `secrets.token_urlsafe(32)` and `invite_expiry() -> datetime` = now + `INVITE_TTL = timedelta(days=7)` (7 days is an assumption, not in the PRD).
  - `Event(organization FK CASCADE related_name="events", name CharField(200), type Type{LEAGUE, TOURNAMENT}, status Status{DRAFT, PUBLISHED, COMPLETED} default DRAFT, start_date DateField, courts PositiveSmallIntegerField(validators=[MinValueValidator(1)]), match_format MatchFormat{SINGLE="single" "1 game", BEST_OF_3="best_of_3" "Best of 3", BEST_OF_5="best_of_5" "Best of 5"} default SINGLE, points_to_win PointsToWin(IntegerChoices 11/15/21) default 11, win_by_two default True, player_score_entry default False, share_token CharField(64, unique, null, blank), window_minutes PositiveIntegerField null blank, game_minutes PositiveIntegerField null blank, created_at auto_now_add)`. `Meta.ordering = ["-start_date", "-id"]` (P2: newest first).
    - `clean()`: a tournament needs `window_minutes`; if `game_minutes` is empty on a tournament, set it to 15.
    - `set_week_count(self, n: int) -> None`: makes the event's `Week` rows exactly `1..n`, adding missing ones with `date = start_date + 7 × (number − 1)` days and deleting numbers above `n`. A tournament is always called with `n = 1`.
  - `Division(event FK CASCADE related_name="divisions", level Level{BEGINNER, INTERMEDIATE, ADVANCED})`. Unique `(event, level)`.
  - `Flight(division FK CASCADE related_name="flights", format Format{MENS="mens" "Men's", WOMENS="womens" "Women's", MIXED="mixed" "Mixed"}, games_per_team_by_week JSONField(default=list, blank=True))`. Unique `(division, format)`. Property `event -> Event`. Property `name -> str` = `"<Level label> <Format label>"`, e.g. `"Intermediate Men's"`. `clean()`: the list must contain only non-negative ints.
  - `Team(flight FK CASCADE related_name="teams", name CharField(120), withdrawn_at DateTimeField null blank)`. Unique `(flight, name)`. `players` = `ManyToManyField(Player, through="TeamMember", related_name="teams")`.
  - `TeamMember(team FK CASCADE related_name="members", player FK Player PROTECT)`. Unique `(team, player)`. `clean()`: a team can't have more than 2 members, and the player must belong to the event's organization.
  - `Week(event FK CASCADE related_name="weeks", number PositiveSmallIntegerField, date DateField null blank, status Status{SCHEDULED, CANCELLED} default SCHEDULED)`. Unique `(event, number)`, ordering `["number"]`.
  - `Match(flight FK CASCADE related_name="matches", week FK Week CASCADE related_name="matches", round_no PositiveSmallIntegerField, court_no PositiveSmallIntegerField, team_a FK Team PROTECT related_name="+", team_b FK Team PROTECT related_name="+", status Status{SCHEDULED, FINAL, CANCELLED, VOID} default SCHEDULED, winner FK Team null blank PROTECT related_name="+", forfeited_by FK Team null blank PROTECT related_name="+", last_edited_by FK User null blank SET_NULL, updated_at auto_now)`. Constraints: `CheckConstraint` `team_a != team_b` (name `match_distinct_teams`), `round_no >= 1` and `court_no >= 1` (`match_round_positive`, `match_court_positive`), unique `(week, round_no, court_no)` (`one_match_per_court_per_round`). Ordering `["week__number", "round_no", "court_no"]`. `clean()`: both teams in `flight`; `week.event == flight.event`; `winner` and `forfeited_by`, when set, are `team_a` or `team_b`.
  - `GameScore(match FK CASCADE related_name="games", game_no PositiveSmallIntegerField(validators 1..5), points_a PositiveSmallIntegerField, points_b PositiveSmallIntegerField)`. Unique `(match, game_no)`, ordering `["game_no"]`.
- Produces, in `tests/factories.py`:
  - `make_event(name="Spring Tuesday League", weeks=4, courts=2, **fields) -> Event` — get-or-creates Organization "Waco Regional", `start_date=date(2027, 3, 2)`, calls `set_week_count(weeks)`
  - `add_player(org: Organization, name: str, email: str = "") -> Player`
  - `add_flight(event, level="intermediate", format="mens", games=(2, 2, 2, 2)) -> Flight` — get-or-creates the Division
  - `add_team(flight, name, players: tuple[Player, Player] | None = None) -> Team` — creates players `"<name> A"`, `"<name> B"` when `None`

Note for later plans: the swap feature must update two matches' slots without breaking `one_match_per_court_per_round` mid-transaction (SQLite can't defer it). Move one to a free temporary slot (e.g. `round_no` set to a value past the night's last round), then write the final slots.

- [ ] **Step 1: Write the failing tests** in `tests/test_league_models.py` (`pytestmark = pytest.mark.django_db`), using the factories:

```python
def test_flight_name_combines_level_and_format():
    assert add_flight(make_event()).name == "Intermediate Men's"

def test_set_week_count_adds_and_removes_weeks():
    event = make_event(weeks=4)
    assert [(w.number, w.date) for w in event.weeks.all()][:2] == [(1, date(2027, 3, 2)), (2, date(2027, 3, 9))]
    event.set_week_count(2)
    assert list(event.weeks.values_list("number", flat=True)) == [1, 2]

def test_event_defaults_match_prd_a3():
    e = make_event()
    assert (e.status, e.match_format, e.points_to_win, e.win_by_two, e.player_score_entry, e.share_token) == ("draft", "single", 11, True, False, None)

def test_tournament_needs_window_and_defaults_game_length():
    e = make_event(type="tournament", weeks=1)
    with pytest.raises(ValidationError): e.full_clean()
    e.window_minutes = 120; e.full_clean()
    assert e.game_minutes == 15

def test_games_per_team_must_be_non_negative_ints():
    f = add_flight(make_event(), games=[2, -1])
    with pytest.raises(ValidationError): f.full_clean()

def test_team_cannot_have_a_third_member():
    team = add_team(add_flight(make_event()), "Dinkers")
    extra = TeamMember(team=team, player=add_player(team.flight.event.organization, "Sam"))
    with pytest.raises(ValidationError): extra.full_clean()

def test_match_teams_must_differ():         # IntegrityError on save with team_a == team_b
def test_one_match_per_court_per_round():   # second Match in same week/round/court → IntegrityError
def test_match_team_from_other_flight_fails_clean():  # ValidationError
def test_match_winner_must_be_in_match():   # ValidationError when winner is a third team
def test_player_email_unique_per_org_but_blank_allowed():
    # two players with email "" in one org: fine; two with "p@x.com": IntegrityError
def test_invite_token_is_long_random_and_expires_in_7_days():
    i = Invite.objects.create(organization=org, email="p@x.com", role="player")
    assert len(i.token) >= 40 and not i.is_expired()
    assert i.is_expired(now=timezone.now() + timedelta(days=8))
def test_deleting_event_removes_its_flights_teams_and_matches():
```

Write the bodies of the one-line tests to assert exactly what their names say.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_league_models.py -v`
Expected: ImportError on `league.models`.

- [ ] **Step 3: Implement the models** exactly as in the Interfaces block, then the factories.

- [ ] **Step 4: Migrate and run the tests**

```powershell
.venv/Scripts/python manage.py makemigrations league
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py makemigrations --check --dry-run
.venv/Scripts/python -m pytest -v
```

Expected: migrate succeeds; `--check` prints "No changes detected"; all tests pass.

- [ ] **Step 5: Commit**

```bash
git add league tests/factories.py tests/test_league_models.py
git commit -m "feat(league): models and migrations for the PRD data model"
```

---

### Task 3: Django admin for data entry

**Files:**
- Modify: `league/admin.py`
- Test: `tests/test_admin.py`

**Interfaces:**
- Consumes: all models from Tasks 1–2.
- Produces registrations (later plans don't depend on them):
  - `EventAdmin`: `list_display = (name, type, status, start_date, courts)`, `list_filter = (type, status)`, inlines `DivisionInline` (tabular) and `WeekInline` (tabular)
  - `FlightAdmin`: `list_display = (__str__, division, games_per_team_by_week)`, inline `TeamInline`
  - `TeamAdmin`: inline `TeamMemberInline` with `min_num = 2`, `max_num = 2`, `validate_min = validate_max = True`, `autocomplete_fields = ["player"]`
  - `PlayerAdmin`: `search_fields = (name, email)`, `list_display = (name, email, organization, user)`
  - `MatchAdmin`: `list_display = (week, round_no, court_no, flight, team_a, team_b, status)`, `list_filter = (status, flight__division__event)`, inline `GameScoreInline`
  - `InviteAdmin`, `WeekAdmin`, `DivisionAdmin`: default with sensible `list_display`
  - Give `Flight`, `Team`, `Division`, `Week`, `Match` readable `__str__` (e.g. `Match`: `"Wk 1 R1 C2: Dinkers v Smashers"`).

- [ ] **Step 1: Write the failing tests** (`tests/test_admin.py`, `admin_client` fixture from pytest-django):

```python
MODELS = ["event", "division", "flight", "team", "player", "invite", "week", "match"]

@pytest.mark.parametrize("model", MODELS)
def test_changelist_loads(admin_client, model):
    make_event()  # so lists aren't empty
    assert admin_client.get(f"/admin/league/{model}/").status_code == 200

def test_team_page_shows_two_member_rows(admin_client):
    team = add_team(add_flight(make_event()), "Dinkers")
    page = admin_client.get(f"/admin/league/team/{team.pk}/change/")
    assert page.status_code == 200 and b"members-1-player" in page.content

def test_user_changelist_loads(admin_client):
    assert admin_client.get("/admin/accounts/user/").status_code == 200
```

(`admin_client` needs `createsuperuser` to work without a username. Task 1's manager covers that. If the fixture fails, set `django_username_field` per the pytest-django docs instead of changing the model.)

- [ ] **Step 2: Run to verify they fail** — `.venv/Scripts/python -m pytest tests/test_admin.py -v` → 404s.
- [ ] **Step 3: Implement the registrations.**
- [ ] **Step 4: Run** `.venv/Scripts/python -m pytest -v` → all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(league): admin registrations for quick data entry"`

---

### Task 4: Scheduling bridge and admin "Generate schedule" action

**Files:**
- Create: `league/scheduling.py`
- Modify: `league/admin.py`
- Test: `tests/test_scheduling_bridge.py`

**Interfaces:**
- Consumes: `scheduler.generate`, `scheduler.Schedule`, `scheduler.Flight`, `scheduler.Team`, `scheduler.Match`, `scheduler.ScheduleError` (see `scheduler/types.py`); models from Task 2.
- Produces, in `league/scheduling.py`:
  - `event_flights(event: Event, include_withdrawn: bool = False) -> list[scheduler.Flight]`
  - `generate_event(event: Event) -> scheduler.Schedule` (atomic; raises `ScheduleError`)
  - `load_schedule(event: Event) -> tuple[scheduler.Schedule, list[scheduler.Flight]]`
- Conversion rules (fixed, so later plans can map back):
  - Flight id = `str(flight.pk)`, name = `flight.name`, `games_per_team_by_week = tuple(flight.games_per_team_by_week)`.
  - Team id = `str(team.pk)`, name = `team.name`, players = the two members' player keys, ordered by `TeamMember.pk`.
  - Player key = `player.name`. If two different `Player` rows in the event share a name, both keys become `"<name> (#<pk>)"`. This keeps scheduler messages readable and keeps different people apart.
  - Order flights by `(division.pk, flight.pk)` and teams by `pk`, so output is deterministic.
- `generate_event` checks, in this order, each raising `ScheduleError` with this text:
  1. no flights → `"Add at least one flight before generating."`
  2. any match in the event with `status = final`, a `GameScore`, or `forfeited_by` set → `"Scores have been entered, so the schedule can't be regenerated. Move individual games instead."`
  3. a non-withdrawn team without exactly 2 members → `"<team> needs exactly 2 players before generating."`
  4. `len(games_per_team_by_week) != event.weeks.count()` → `"<flight name> has games for <x> weeks but the event has <n>."`
  5. then `scheduler.generate(flights, event.courts)` (its own errors pass through unchanged)

  On success it deletes **all** of the event's `Match` rows and `bulk_create`s one per scheduler match: week from the event's `Week` by number, teams by pk. All of this runs in one `transaction.atomic()`. It does not change `event.status`.
- `load_schedule` uses `event_flights(event, include_withdrawn=True)`, reads matches with status `scheduled` or `final`, and returns a `Schedule` with `courts = event.courts`.

- [ ] **Step 1: Write the failing tests** in `tests/test_scheduling_bridge.py` (`pytestmark = pytest.mark.django_db`). Use `scheduler.fairness_report` and the T-case properties; don't assert exact pairings.

```python
def t1_event():  # PRD T1: 4 teams, 4 weeks, 2 games/team/week, 2 courts
    event = make_event(weeks=4, courts=2)
    flight = add_flight(event, games=[2, 2, 2, 2])
    for n in ["Dinkers", "Smashers", "Lobsters", "Kitchen Kings"]: add_team(flight, n)
    return event

def test_t1_through_database():
    event = t1_event()
    generate_event(event)
    matches = Match.objects.filter(flight__division__event=event)
    assert matches.count() == 16
    for week in event.weeks.all():
        assert {m.round_no for m in matches.filter(week=week)} == {1, 2}
        assert all(m.court_no in (1, 2) for m in matches.filter(week=week))

def test_regenerating_replaces_matches():
    event = t1_event(); generate_event(event); generate_event(event)
    assert Match.objects.filter(flight__division__event=event).count() == 16

def test_regenerate_blocked_once_a_score_exists():
    event = t1_event(); generate_event(event)
    m = Match.objects.first(); GameScore.objects.create(match=m, game_no=1, points_a=11, points_b=7)
    with pytest.raises(ScheduleError, match="Scores have been entered"): generate_event(event)
    assert Match.objects.filter(flight__division__event=event).count() == 16  # untouched

def test_regenerate_allowed_after_publish_without_scores():  # status=published, no scores → succeeds

def test_t5_player_on_mens_and_mixed_never_double_booked():
    event = make_event(weeks=1, courts=4)
    mens, mixed = add_flight(event, format="mens", games=[2]), add_flight(event, format="mixed", games=[2])
    pat = add_player(event.organization, "Pat Lee")
    add_team(mens, "Dinkers", (pat, add_player(event.organization, "Max"))); # + 3 more men's teams
    add_team(mixed, "Volley Llamas", (pat, add_player(event.organization, "Ana"))); # + 3 more mixed teams
    generate_event(event)
    pat_rounds = [m.round_no for m in Match.objects.all() if pat in (*m.team_a.players.all(), *m.team_b.players.all())]
    assert len(pat_rounds) == 4 and len(set(pat_rounds)) == 4

def test_two_different_players_with_same_name_are_not_one_person():
    # Men's team has a "Pat Lee", a separate Mixed team has a different Player also named "Pat Lee";
    # assert generation succeeds and event_flights gives them keys "Pat Lee (#<pk1>)" and "Pat Lee (#<pk2>)".

def test_team_with_one_player_is_rejected():
    event = t1_event(); team = Team.objects.get(name="Dinkers"); team.members.last().delete()
    with pytest.raises(ScheduleError, match="Dinkers needs exactly 2 players before generating."): generate_event(event)

def test_withdrawn_team_is_left_out_of_generation():  # 5 teams, one withdrawn → 4-team schedule, no matches for it

def test_week_count_mismatch_names_the_flight():
    event = t1_event(); event.set_week_count(3)
    with pytest.raises(ScheduleError, match="Intermediate Men's has games for 4 weeks but the event has 3."): generate_event(event)

def test_no_flights():          # "Add at least one flight before generating."
def test_fewer_than_two_teams_message_passes_through():  # "Add at least 2 teams to Intermediate Men's before generating."

def test_load_schedule_round_trips():
    event = t1_event(); generated = generate_event(event)
    loaded, flights = load_schedule(event)
    assert loaded == generated and [f.name for f in flights] == ["Intermediate Men's"]

def test_generation_is_deterministic():
    event = t1_event(); first = generate_event(event); assert generate_event(event) == first

def test_admin_generate_action(admin_client):
    event = t1_event()
    r = admin_client.post("/admin/league/event/", {"action": "generate_schedule", "_selected_action": [event.pk]}, follow=True)
    assert b"Generated 16 games for Spring Tuesday League." in r.content

def test_admin_generate_action_shows_errors(admin_client):
    event = make_event()   # no flights
    r = admin_client.post("/admin/league/event/", {"action": "generate_schedule", "_selected_action": [event.pk]}, follow=True)
    assert b"Spring Tuesday League: Add at least one flight before generating." in r.content
```

Fill in the bodies marked with comments so they assert what the names say.

- [ ] **Step 2: Run to verify they fail** — `.venv/Scripts/python -m pytest tests/test_scheduling_bridge.py -v` → ImportError on `league.scheduling`.
- [ ] **Step 3: Implement `league/scheduling.py`** per the Interfaces block. Use `select_related`/`prefetch_related` so one event loads in a fixed number of queries. Scheduler `Match` objects map back to rows through dicts keyed by team id and week number.
- [ ] **Step 4: Add the admin action** `EventAdmin.generate_schedule` (description "Generate schedule"). For each selected event, call `generate_event`. On success send `messages.SUCCESS` `"Generated <n> games for <event name>."`; on `ScheduleError` send `messages.ERROR` `"<event name>: <error text>"`.
- [ ] **Step 5: Run** `.venv/Scripts/python -m pytest -v` → all pass.
- [ ] **Step 6: Commit** — `git commit -m "feat(league): generate schedules from the database and save them as matches"`

---

### Task 5: Demo seed command

**Files:**
- Create: `league/management/__init__.py`, `league/management/commands/__init__.py`, `league/management/commands/seed_demo.py`
- Test: `tests/test_seed.py`

**Interfaces:**
- Consumes: models, `Event.set_week_count`, `generate_event`.
- Produces: `python manage.py seed_demo [--reset]`.

Demo contents (fixed, so the tests can count them):
- Organization `"Waco Regional (Demo)"` (never the real facility's name). Refuses to run unless `settings.DEBUG` is on or `--force` is given (stderr `seed_demo only runs with DEBUG on. Use --force to run it anyway.`, then `CommandError`). User `admin@example.com`, password `pickleball`, `is_admin`, `is_staff` and `is_superuser` all true, in that org.
- League `"Spring Tuesday League"`: start 2027-03-02 (a Tuesday), 4 weeks, 6 courts, left as `draft` (publishing comes in a later plan). Divisions Beginner, Intermediate, Advanced, each with Men's and Mixed flights. Team counts per flight, in that order: 4, 5, 6, 4, 5, 6. Games per team `[2, 2, 2, 2]`. Every team has two distinct players. In each division, one player is on both the Men's and the Mixed team (T5).
- Tournament `"March Madness Shootout"`: 2027-03-13, 1 week, 4 courts, `window_minutes=120`, `game_minutes=15`. One Intermediate Mixed flight with 8 teams and games `[7]` (a full round robin: 28 games, 7 rounds, 105 minutes).
- Both events are generated. Expected matches: league 4 weeks × 2 × (2+2+3+2+2+3) = 112, tournament 28, **total 140**.
- Team and player names come from fixed lists in the command (no randomness).
- If an Organization named "Waco Regional (Demo)" already exists and `--reset` isn't given: print `Demo data already exists. Use --reset to rebuild it.` and change nothing. With `--reset`: delete that organization (cascades to its events and players) and the `admin@example.com` user, then rebuild. An existing `admin@example.com` without the org is updated (password, flags, org) rather than recreated.
- On success it prints `Seeded 2 events, 7 flights, 140 games. Log in at /admin/ as admin@example.com / pickleball`.
- Runs inside one `transaction.atomic()`.

- [ ] **Step 1: Write the failing tests** (`tests/test_seed.py`, `pytestmark = pytest.mark.django_db`, using `call_command` and `capsys`):

```python
def test_seed_creates_demo():
    call_command("seed_demo")
    assert Event.objects.count() == 2 and Flight.objects.count() == 7 and Match.objects.count() == 140
    assert User.objects.get(email="admin@example.com").check_password("pickleball")

def test_seed_league_has_a_player_on_two_flights_each_division():
    call_command("seed_demo")
    league = Event.objects.get(name="Spring Tuesday League")
    for division in league.divisions.all():
        assert Player.objects.filter(teams__flight__division=division).annotate(n=Count("teams")).filter(n=2).exists()

def test_seed_twice_does_not_duplicate(capsys):
    call_command("seed_demo"); call_command("seed_demo")
    assert "Demo data already exists. Use --reset to rebuild it." in capsys.readouterr().out
    assert Match.objects.count() == 140

def test_seed_reset_rebuilds():
    call_command("seed_demo"); call_command("seed_demo", "--reset")
    assert Event.objects.count() == 2 and Match.objects.count() == 140 and User.objects.count() == 1
```

- [ ] **Step 2: Run to verify they fail** — `Unknown command: 'seed_demo'`.
- [ ] **Step 3: Implement the command.**
- [ ] **Step 4: Run the full suite and the real command**

```powershell
.venv/Scripts/python -m pytest -v
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py seed_demo
.venv/Scripts/python manage.py check
```

Expected: all tests pass; the seed prints the success line. Start `runserver`, log in at `/admin/` and confirm the Match list shows the Spring Tuesday League's week 1 games.

- [ ] **Step 5: Tick the build checklist.** In the PRD's Section 8 checklist, mark "Models and migrations for the ERD…" and "Seed script…" done (`- [x]`).
- [ ] **Step 6: Commit** — `git commit -m "feat(league): seed_demo command with a 6-flight league and a tournament"`
