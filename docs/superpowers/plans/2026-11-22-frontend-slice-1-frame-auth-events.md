# Front-End Slice 1: Frame, Auth and My Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Stryde look and app frame (theme, three base templates, phone tab bar and laptop top bar by role), the login / invite / password-reset pages, and P2 My Events with its empty state. After this slice, a director can log in and see their events, and a player can accept an invite and land on a My Games page.

**Architecture:** A new `ui` app owns everything frame-level: the `{% icon %}` tag, the nav model (`ui/nav.py`) and its context processor. Templates live in the project `templates/` folder. Tailwind v4 is compiled by `django-tailwind-cli` from `frontend/stryde.css`, which imports a vendored Basecoat file and holds the Stryde tokens. Auth views go in `accounts`, and P2 and the `/me` page go in `league`. Nav items and page links that point at pages a later slice builds are hidden automatically: anything whose URL name doesn't reverse is dropped. Later slices just add their URL and the link appears.

**Tech Stack:** Python 3.13, Django 6.1, django-tailwind-cli 4.8.3 (Tailwind 4.3.5 standalone binary, no Node), Basecoat 1.1.0, HTMX 2.0.11, Lucide icons 1.66.0, self-hosted Inter and Montserrat (Fontsource 5.3.0), pytest 9 + pytest-django 4.14.

**Spec:** `docs/superpowers/specs/2026-11-19-front-end-design-system-design.md` (slice 1 of §8), with `Pickleball League Manager — PRD, ERD & Scheduling Spec.md` §2 (roles), §3 (navigation), Flow D, and §5 P1/P2/P11.

## Global Constraints

- Run all Python through the venv: `.venv/Scripts/python`. Tests: `.venv/Scripts/python -m pytest` from the repo root. The full suite (scheduler, models, admin, seed) must keep passing after every task.
- Pinned, vendored, no CDN at runtime: django-tailwind-cli `==4.8.3`, `TAILWIND_CLI_VERSION = "4.3.5"`, Basecoat `1.1.0`, HTMX `2.0.11`, Lucide `1.66.0`, `@fontsource-variable/inter@5.3.0`, `@fontsource/montserrat@5.3.0`. No request to Google Fonts or any CDN from a rendered page.
- Theme tokens, exact values: `--color-ink #0B1A4A`, `--color-brand #0B3DCC`, `--color-progress #14E2B8`, `--color-action #FF7A3D`, `--color-surface #F6F8FC`, `--color-card #FFFFFF`, `--color-border #E3E8F2`, `--color-warn #8A5A00`, `--color-warn-bg #FFF4E0`, `--color-danger #E5484D`. Card shadow `0 1px 3px rgb(11 26 74 / .08)`. Cards 12–14px radius, inputs 8–10px, buttons and tabs pill.
- Templates never contain raw hex colors. They use Stryde token utilities (`bg-brand`, `text-ink`, …) or Basecoat classes. Tailwind class strings live in templates or `frontend/stryde.css`, never in Python, because Tailwind only scans those.
- Contrast: Coral (`action`) and Teal (`progress`) fills always carry `text-ink`. Teal and Coral are never text colors on white. Cobalt fill takes white text.
- Product name in the UI is **Stryde**. Page `<title>` is `<page> · Stryde`.
- Breakpoint is Tailwind `md` (768px): below it the bottom tab bar, at or above it the top bar.
- Fonts: Montserrat 700/800 for page titles, card titles and big numbers (`font-display`); Inter for everything else (`font-sans`).
- Components are includes in `templates/components/`, called as `{% include "components/x.html" with … only %}`. Build each one when its first page needs it. The skeleton component waits for the first HTMX-loaded page (P4). P2 renders server-side, so it has no loading state of its own.
- URLs use Django's trailing slash. PRD routes like `/login` and `/events` reach them through `APPEND_SLASH`.
- URL names this slice defines: `home`, `login`, `logout`, `account`, `password_reset`, `password_reset_done`, `password_reset_confirm`, `password_reset_complete`, `invite_accept`, `event_list`, `my_games`. URL names reserved for later slices (nav and links pick them up when they exist): `event_create`, `event_preview` (pk), `event_schedule` (pk), `tonight`, `my_standings`, `player_list`, `admin_list`.
- PRD copy, verbatim: "No events yet. Create your first league or tournament." · "You're not on any teams yet." · "Something went wrong loading this page. Refresh to try again." · "This invite link has expired. Ask your league admin to resend it." · "That email already has an account — log in instead."
- `TIME_ZONE = "America/Chicago"` (already set). Email stays on the console backend.
- Deferred requirements from project memory (row locking on score save, the A13 edit guard, `game_minutes=None` → 15, `RestrictedError`) don't apply to this slice. Don't touch them.

## Review Focus

1. **Email letter case.** An invite for `Pat@Example.com` when `pat@example.com` already has an account must show "That email already has an account — log in instead.", and logging in as `PAT@example.com` must work. (Tasks 5 and 6)
2. **The same invite submitted twice** (double tap, two tabs). Exactly one user is created; the second submit sees "This invite has already been used. Log in instead." (Task 6)
3. **An admin with no organization** (made by `createsuperuser`) opens My Events and sees the empty state, not a crash. Events of another organization never appear. (Task 4)
4. **A player whose only team is in a draft event** sees "You're not on any teams yet."; drafts are not visible to players. A player opening `/events/` gets the styled 403 page. (Task 4)
5. **Nav items for pages not built yet** (Players, Admins, Tonight, Standings) are hidden. They must not raise `NoReverseMatch` on every page. (Task 2)

## File Structure

| File | Responsibility |
| --- | --- |
| `pyproject.toml`, `.gitignore`, `README.md` | Dependency, ignore compiled CSS, dev commands |
| `config/settings.py`, `config/urls.py` | Apps, static dirs, Tailwind settings, context processor, login URLs, include app URLs, admin header |
| `frontend/stryde.css`, `frontend/vendor/basecoat-1.1.0.css` | Tailwind source: tokens, Basecoat import and mapping, Stryde component classes |
| `static/vendor/…`, `static/fonts/…`, `static/brand/…` | Vendored JS, fonts, logos |
| `ui/templatetags/ui.py`, `ui/icons/*.svg` | `{% icon %}` tag and the Lucide icons it inlines |
| `ui/nav.py`, `ui/context_processors.py` | Nav items per role, `optional_reverse`, the `nav` template variable |
| `accounts/roles.py`, `accounts/permissions.py` | `role_of`, `player_for`, `admin_required` |
| `accounts/views.py`, `accounts/forms.py`, `accounts/urls.py`, `accounts/invites.py` | Home redirect, login/logout/account, password reset, invite acceptance |
| `league/views.py`, `league/urls.py`, `league/display.py` | P2 My Events, `/me` My Games (first version), date-range text |
| `templates/base.html`, `base_app.html`, `base_public.html` | The three frames |
| `templates/components/*.html` | error_state, empty_state, status_badge, form_field |
| `templates/403.html`, `404.html`, `500.html`, `templates/registration/*`, `templates/accounts/*`, `templates/league/*` | Pages |
| `tests/future_urls.py`, `tests/nav_urls_partial.py`, `tests/error_urls.py` | URL confs that tests swap in |
| `tests/test_frame.py`, `test_nav.py`, `test_layouts.py`, `test_my_events.py`, `test_auth_pages.py`, `test_invites.py` | One test file per task |

---

### Task 1: Tooling, theme tokens and `base.html`

**Files:**
- Modify: `pyproject.toml`, `.gitignore`, `config/settings.py`, `config/urls.py`
- Create: `ui/__init__.py`, `ui/apps.py`, `ui/templatetags/__init__.py`, `ui/templatetags/ui.py`, `ui/icons/*.svg`, `frontend/stryde.css`, `frontend/vendor/basecoat-1.1.0.css`, `static/vendor/*`, `static/fonts/*`, `static/brand/*`, `templates/base.html`
- Test: `tests/test_frame.py`

**Interfaces:**
- Produces: template tag library `ui` with `{% icon "<name>" class="<extra classes>" %}`, which returns the inlined SVG and raises `ValueError(f"Unknown icon: {name}")` for a missing file. `base.html` blocks: `title`, `body_class`, `body`. Tailwind utilities from the tokens: `bg-/text-/border-` + `ink`, `brand`, `progress`, `action`, `surface`, `warn`, `warn-bg`, `danger`, plus Basecoat's `card` and `border`. Font utilities `font-sans` (Inter) and `font-display` (Montserrat).

- [ ] **Step 1: Write the failing tests** in `tests/test_frame.py`

```python
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.template.loader import render_to_string

VENDORED = [
    "vendor/htmx-2.0.11.min.js",
    "vendor/basecoat-1.1.0/basecoat.min.js",
    "vendor/basecoat-1.1.0/dropdown-menu.min.js",
    "vendor/basecoat-1.1.0/toast.min.js",
    "fonts/inter-latin-wght-normal.woff2",
    "fonts/montserrat-latin-700-normal.woff2",
    "fonts/montserrat-latin-800-normal.woff2",
    "brand/stryde-logo.svg",
    "brand/stryde-logo-one-color.svg",
    "brand/stryde-monogram.svg",
]

def test_vendored_files_exist():
    for path in VENDORED:
        assert finders.find(path), path

def test_base_loads_local_assets_only():
    html = render_to_string("base.html")
    for path in ["css/stryde.css", *VENDORED[:5], "brand/stryde-monogram.svg"]:
        assert path in html, path
    assert "jsdelivr" not in html and "googleapis" not in html and "unpkg" not in html

def test_base_title_suffix():
    html = Template('{% extends "base.html" %}{% block title %}My Events{% endblock %}').render(Context())
    assert "<title>My Events · Stryde</title>" in html

def test_icon_tag_inlines_svg():
    out = Template('{% load ui %}{% icon "plus" class="size-4" %}').render(Context())
    assert out.lstrip().startswith("<svg")
    assert 'class="lucide lucide-plus size-4"' in out
    assert 'aria-hidden="true"' in out
    assert "@license" not in out

def test_icon_tag_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown icon: nope"):
        Template('{% load ui %}{% icon "nope" %}').render(Context())

def test_theme_tokens_match_spec():
    css = Path(settings.BASE_DIR, "frontend", "stryde.css").read_text().lower()
    for token, value in [
        ("--color-ink", "#0b1a4a"), ("--color-brand", "#0b3dcc"),
        ("--color-progress", "#14e2b8"), ("--color-action", "#ff7a3d"),
        ("--color-surface", "#f6f8fc"), ("--color-warn", "#8a5a00"),
        ("--color-warn-bg", "#fff4e0"), ("--color-danger", "#e5484d"),
        ("--card", "#ffffff"), ("--border", "#e3e8f2"),
    ]:
        assert f"{token}: {value};" in css, token

def test_templates_use_no_raw_hex():
    hexcolor = re.compile(r"#[0-9A-Fa-f]{6}\b")
    for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
        assert not hexcolor.search(path.read_text(encoding="utf-8")), path

def test_admin_header_is_stryde():
    assert admin.site.site_header == "Stryde"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_frame.py -v`
Expected: FAIL (template `base.html` not found, no `ui` library).

- [ ] **Step 3: Install and configure**

- `pyproject.toml` dependencies: add `"django-tailwind-cli==4.8.3"`. Install with `.venv/Scripts/python -m pip install "django-tailwind-cli==4.8.3"`.
- `config/settings.py`: add `"django_tailwind_cli"` and `"ui"` to `INSTALLED_APPS`; `STATICFILES_DIRS = [BASE_DIR / "static"]`; `TAILWIND_CLI_VERSION = "4.3.5"`; `TAILWIND_CLI_SRC_CSS = "frontend/stryde.css"`; `TAILWIND_CLI_DIST_CSS = "css/stryde.css"`.
- `.gitignore`: add `static/css/stryde.css` (built output).
- `config/urls.py`: `admin.site.site_header = "Stryde"`, `admin.site.site_title = "Stryde admin"`.

- [ ] **Step 4: Vendor the assets** (Bash; jsdelivr serves the npm packages)

```bash
NPM=https://cdn.jsdelivr.net/npm
mkdir -p static/vendor/basecoat-1.1.0 static/fonts static/brand frontend/vendor ui/icons
curl -fsSL $NPM/htmx.org@2.0.11/dist/htmx.min.js -o static/vendor/htmx-2.0.11.min.js
for f in basecoat dropdown-menu toast; do curl -fsSL $NPM/basecoat-css@1.1.0/dist/js/$f.min.js -o static/vendor/basecoat-1.1.0/$f.min.js; done
curl -fsSL $NPM/basecoat-css@1.1.0/dist/basecoat.bundle.css -o frontend/vendor/basecoat-1.1.0.css
curl -fsSL $NPM/@fontsource-variable/inter@5.3.0/files/inter-latin-wght-normal.woff2 -o static/fonts/inter-latin-wght-normal.woff2
for w in 700 800; do curl -fsSL $NPM/@fontsource/montserrat@5.3.0/files/montserrat-latin-$w-normal.woff2 -o static/fonts/montserrat-latin-$w-normal.woff2; done
for i in calendar-days moon users shield trophy chart-column user-round ellipsis log-out plus calendar-plus triangle-alert; do curl -fsSL $NPM/lucide-static@1.66.0/icons/$i.svg -o ui/icons/$i.svg; done
cp design_ideas/Stryde_Official_Logo.svg static/brand/stryde-logo.svg
cp design_ideas/Stryde_Official_Logo_One_Color.svg static/brand/stryde-logo-one-color.svg
cp design_ideas/Stryde_Official_Monogram.svg static/brand/stryde-monogram.svg
```

- [ ] **Step 5: Write `frontend/stryde.css`**

The file has four parts, in this order:
1. `@import "tailwindcss";`, then `@import "./vendor/basecoat-1.1.0.css";`, then `@source "../templates";`.
2. Stryde tokens:

```css
@theme {
  --color-ink: #0B1A4A;
  --color-brand: #0B3DCC;
  --color-progress: #14E2B8;
  --color-action: #FF7A3D;
  --color-surface: #F6F8FC;
  --color-warn: #8A5A00;
  --color-warn-bg: #FFF4E0;
  --color-danger: #E5484D;
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-display: "Montserrat", "Inter", ui-sans-serif, sans-serif;
  --shadow-card: 0 1px 3px rgb(11 26 74 / .08);
}
```

3. A `:root` block that maps Basecoat's variables onto Stryde. It comes after the import, so it wins. Write literal values, lower-case hex, as `name: value;`: `--background: #f6f8fc; --foreground: #0b1a4a; --card: #ffffff; --card-foreground: #0b1a4a; --popover: #ffffff; --popover-foreground: #0b1a4a; --primary: #ff7a3d; --primary-foreground: #0b1a4a; --secondary: #0b3dcc; --secondary-foreground: #ffffff; --muted: #eef2f9; --muted-foreground: #5a6480; --accent: #e8eefc; --accent-foreground: #0b3dcc; --destructive: #e5484d; --border: #e3e8f2; --input: #e3e8f2; --ring: #0b3dcc; --radius: 0.75rem;`. Don't redefine `--color-card` or `--color-border` in `@theme`; Basecoat already derives them from `--card` and `--border`.
4. `@layer components`: Basecoat `.btn*` classes become pills (`border-radius: 9999px`), `.card` gets `box-shadow: var(--shadow-card)` and a 14px radius, inputs get a 10px radius, and `h1, .font-display` use `font-display`.

- [ ] **Step 6: Implement the `icon` tag** in `ui/templatetags/ui.py`

`@register.simple_tag def icon(name: str, class_: str = "") -> SafeString`. The template keyword is `class=`, so take `**kwargs` and read `kwargs.get("class", "")`. Read `ui/icons/<name>.svg` through an `functools.lru_cache` helper, drop the `<!-- @license … -->` comment, put the extra classes after `lucide lucide-<name>` in the `class` attribute, add `aria-hidden="true"`, and return `mark_safe`. Reject names that aren't `[a-z0-9-]+`.

- [ ] **Step 7: Write `templates/base.html`**

The head holds the charset, `viewport` (`width=device-width, initial-scale=1`), `<title>{% block title %}{% endblock %} · Stryde</title>`, the favicon `brand/stryde-monogram.svg` (`type="image/svg+xml"`) and an inline `<style>` with three `@font-face` rules. Their `src` comes from `{% static %}`: Inter with `font-weight: 100 900`, Montserrat 700 and Montserrat 800, all `font-display: swap`. Then `{% load tailwind_cli %}{% tailwind_css %}`. Last come the deferred scripts in this order: htmx, `basecoat.min.js`, `dropdown-menu.min.js`, `toast.min.js`.

`<body class="bg-background text-foreground font-sans antialiased {% block body_class %}{% endblock %}" hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`, then `{% block body %}{% endblock %}`. After the block comes the toaster: `<div id="toaster" class="toaster">` holding one Basecoat `.toast` per Django message, with `data-category` set to the message's level tag (`success`/`info`/`warning`/`error`). The toaster sits at the bottom on phones and top-right at `md`. Tune Basecoat's toaster position in `stryde.css` if needed.

- [ ] **Step 8: Run tests and check**

Run: `.venv/Scripts/python -m pytest tests/test_frame.py -v` → all PASS.
Run: `.venv/Scripts/python manage.py check` → no issues (in particular no `django_tailwind_cli.W001`).
Run: `.venv/Scripts/python manage.py tailwind build` → it downloads the 4.3.5 binary and writes `static/css/stryde.css`. Run `grep -c "color-brand" static/css/stryde.css` and expect at least 1.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .gitignore config ui frontend static templates/base.html tests/test_frame.py
git commit -m "feat(ui): Tailwind + Basecoat tooling, Stryde theme tokens and base template"
```

---

### Task 2: Roles, permissions and the nav model

**Files:**
- Create: `accounts/roles.py`, `accounts/permissions.py`, `ui/nav.py`, `ui/context_processors.py`, `tests/future_urls.py`, `tests/nav_urls_partial.py`
- Modify: `config/settings.py` (add `"ui.context_processors.nav"`)
- Test: `tests/test_nav.py`

**Interfaces:**
- Produces, `accounts/roles.py`:
  - `player_for(user) -> Player | None`: returns `user.player` if it's linked. Otherwise it returns the `Player` in `user.organization` whose email matches `user.email` case-insensitively. It returns `None` for anonymous users and for users with no organization.
  - `role_of(user) -> Literal["admin", "admin_player", "player"]`: `is_admin` plus a player gives `"admin_player"`, `is_admin` alone gives `"admin"`, anyone else gives `"player"`.
- Produces, `accounts/permissions.py`: `admin_required(view)`. Anonymous users get redirected to `settings.LOGIN_URL` with `?next=`. Logged-in non-admins get `PermissionDenied`.
- Produces, `ui/nav.py`:
  - `optional_reverse(name: str, *args) -> str | None`: `reverse`, or `None` on `NoReverseMatch`.
  - `@dataclass(frozen=True) class NavLink: label: str; url: str; icon: str; active: bool`
  - `@dataclass(frozen=True) class Nav: top: list[NavLink]; tabs: list[NavLink]; more: list[NavLink]; account: NavLink | None`
  - `nav_for(user, current_url_name: str | None) -> Nav`. Items whose URL name doesn't reverse are dropped.
- Produces, `ui/context_processors.py`: `nav(request) -> {"nav": Nav | None}`. The value is `None` for anonymous users. `current_url_name` comes from `request.resolver_match.url_name` and is `None` when there's no match.

The items per role are the spec's §5.2 lists. Each entry is (label, URL name, icon):

| Role | `top` | `tabs` | `more` |
| --- | --- | --- | --- |
| admin | My Events·event_list·calendar-days, Players·player_list·users, Admins·admin_list·shield | Events·event_list·calendar-days, Tonight·tonight·moon, Players·player_list·users | Admins·admin_list·shield, Account·account·user-round |
| admin_player | My Events, My Games·my_games·trophy, Players, Admins | Events, Tonight, My Games | Players, Admins, Account |
| player | My Games | My Games, Standings·my_standings·chart-column, Account·account·user-round | (empty) |

`account` is always `Account·account·user-round`; on laptop widths the top bar's account menu uses it. Log out is a POST form in the templates, not a `NavLink`.

- [ ] **Step 1: Write the test URL confs**

`tests/future_urls.py`: `urlpatterns` = `config.urls.urlpatterns` plus a dummy `HttpResponse` view for every URL name in the Global Constraints lists that doesn't already reverse against `config.urls`. Paths: `events/`, `events/new/`, `events/<int:pk>/preview/`, `events/<int:pk>/schedule/`, `tonight/`, `standings/`, `players/`, `admins/`, `me/`, `account/`, `login/`, `logout/`. That makes the test file work at every point in the slice. `tests/nav_urls_partial.py` holds only `event_list` (`events/`) and `account` (`account/`).

- [ ] **Step 2: Write the failing tests** in `tests/test_nav.py`

```python
import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.models import Organization, User
from accounts.permissions import admin_required
from accounts.roles import player_for, role_of
from league.models import Player
from ui.nav import nav_for

pytestmark = pytest.mark.django_db

def labels(links):
    return [link.label for link in links]

@pytest.fixture
def org():
    return Organization.objects.create(name="Waco Regional")

def make_user(org, email, is_admin=False):
    return User.objects.create_user(email, "pw", organization=org, is_admin=is_admin)

def test_role_admin(org):
    assert role_of(make_user(org, "a@example.com", is_admin=True)) == "admin"

def test_role_admin_player_by_email_any_case(org):
    Player.objects.create(organization=org, name="Ann", email="Ann@Example.com")
    user = make_user(org, "ann@example.com", is_admin=True)
    assert role_of(user) == "admin_player"
    assert player_for(user).name == "Ann"

def test_player_in_other_org_does_not_count(org):
    other = Organization.objects.create(name="Elsewhere")
    Player.objects.create(organization=other, name="Ann", email="ann@example.com")
    assert player_for(make_user(org, "ann@example.com", is_admin=True)) is None

def test_user_without_org_has_no_player():
    assert player_for(User.objects.create_user("x@example.com", "pw")) is None

@pytest.mark.urls("tests.future_urls")
def test_admin_nav(org):
    nav = nav_for(make_user(org, "a@example.com", is_admin=True), None)
    assert labels(nav.top) == ["My Events", "Players", "Admins"]
    assert labels(nav.tabs) == ["Events", "Tonight", "Players"]
    assert labels(nav.more) == ["Admins", "Account"]
    assert nav.account.label == "Account"

@pytest.mark.urls("tests.future_urls")
def test_admin_player_nav(org):
    Player.objects.create(organization=org, name="Ann", email="ann@example.com")
    nav = nav_for(make_user(org, "ann@example.com", is_admin=True), None)
    assert labels(nav.top) == ["My Events", "My Games", "Players", "Admins"]
    assert labels(nav.tabs) == ["Events", "Tonight", "My Games"]
    assert labels(nav.more) == ["Players", "Admins", "Account"]

@pytest.mark.urls("tests.future_urls")
def test_player_nav(org):
    nav = nav_for(make_user(org, "p@example.com"), None)
    assert labels(nav.top) == ["My Games"]
    assert labels(nav.tabs) == ["My Games", "Standings", "Account"]
    assert nav.more == []

@pytest.mark.urls("tests.nav_urls_partial")
def test_unbuilt_pages_are_hidden(org):
    nav = nav_for(make_user(org, "a@example.com", is_admin=True), None)
    assert labels(nav.top) == ["My Events"]
    assert labels(nav.tabs) == ["Events"]
    assert labels(nav.more) == ["Account"]

@pytest.mark.urls("tests.future_urls")
def test_active_item(org):
    nav = nav_for(make_user(org, "a@example.com", is_admin=True), "event_list")
    assert [link.active for link in nav.tabs] == [True, False, False]

def test_admin_required(org):
    view = admin_required(lambda request: HttpResponse("ok"))
    request = RequestFactory().get("/events/")
    request.user = AnonymousUser()
    assert view(request).status_code == 302
    request.user = make_user(org, "p@example.com")
    with pytest.raises(PermissionDenied):
        view(request)
    request.user = make_user(org, "a@example.com", is_admin=True)
    assert view(request).content == b"ok"
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_nav.py -v` → FAIL (`accounts.roles` missing).

- [ ] **Step 4: Implement** `accounts/roles.py`, `accounts/permissions.py`, `ui/nav.py` and `ui/context_processors.py` with the signatures above. Register the context processor in `TEMPLATES[0]["OPTIONS"]["context_processors"]`. `admin_required` wraps `login_required`. Cache `player_for` on the user object (`user._stryde_player`) so one request doesn't query it twice.

- [ ] **Step 5: Run tests** → `.venv/Scripts/python -m pytest tests/test_nav.py -v` PASS, then the full suite PASS.

- [ ] **Step 6: Commit**

```bash
git add accounts/roles.py accounts/permissions.py ui config/settings.py tests/future_urls.py tests/nav_urls_partial.py tests/test_nav.py
git commit -m "feat(ui): role-aware nav model that hides pages later slices build"
```

---

### Task 3: App and public frames, toasts, error pages

**Files:**
- Create: `templates/base_app.html`, `templates/base_public.html`, `templates/components/error_state.html`, `templates/403.html`, `templates/404.html`, `templates/500.html`, `tests/error_urls.py`
- Test: `tests/test_layouts.py`

**Interfaces:**
- Consumes: `nav` context variable (Task 2), `{% icon %}` (Task 1).
- Produces: `base_app.html` blocks `title`, `page_title` (the `<h1>`), `page_meta`, `page_actions`, `content`. `base_public.html` blocks `title`, `public_header` (defaults to the monogram; share-link slices put the event name here), `content`. Test hooks: `data-nav="top"`, `data-nav="tabs"`, `data-nav="more"`, and `aria-current="page"` on the active link. `components/error_state.html` takes `title`, `message`.

Frame layout:
- **`base_app.html`** extends `base.html`.
  - **Laptop top bar** (`<header data-nav="top" class="hidden md:flex …">`): `brand/stryde-logo.svg` (monogram + wordmark) linking to `home`, then `nav.top` links (active = Cobalt text with underline), then an account menu on the right (Basecoat dropdown-menu) with `nav.account` and a Log out form.
  - **Phone header** (`md:hidden`): the monogram only.
  - **`<main class="mx-auto max-w-[1200px] px-4 pb-24 md:pb-10">`**: the page title in `font-display` (`text-[22px] font-extrabold` on phone), the meta line in `text-muted-foreground`, actions on the right, then `content`.
  - **Phone tab bar** (`<nav data-nav="tabs" class="md:hidden fixed inset-x-0 bottom-0 bg-card border-t …">`): each of `nav.tabs` shows its icon over its label, and the active one is `text-brand`. A **More** tab (`ellipsis`) appears only when `nav.more` isn't empty. It opens a Basecoat dropdown above the bar (`data-nav="more"`) that lists `nav.more` and the Log out form.
  - Log out is always `<form method="post" action="{% url 'logout' %}">{% csrf_token %}<button …>Log out</button></form>`. Use `{% url 'logout' as logout_url %}` and render the form only when `logout_url` is set, because Task 5 adds that URL.
- **`base_public.html`** extends `base.html`: the `public_header` block centered at the top, then a centered column (`max-w-md`, `px-4`) for `content`. It has no top bar and no tab bar.
- **Error pages** extend `base_public.html` and include `components/error_state.html` (icon `triangle-alert`, title, message, and a "Go to Stryde home" link to `/`):
  - 403: "No access" / "You don't have access to this page."
  - 404: "Page not found" / "We couldn't find that page."
  - 500: "Something went wrong" / "Something went wrong loading this page. Refresh to try again."
  - Django renders `500.html` with an empty context, so it must not need `request`, `nav` or `user`.

- [ ] **Step 1: Write `tests/error_urls.py`**: it holds `config.urls.urlpatterns` plus `boom/` (raises `RuntimeError`) and `forbidden/` (raises `PermissionDenied`).

- [ ] **Step 2: Write the failing tests** in `tests/test_layouts.py`

```python
import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template import engines
from django.test import Client, RequestFactory
from django.urls import resolve

from accounts.models import Organization, User

pytestmark = pytest.mark.django_db
APP_PAGE = '{% extends "base_app.html" %}{% block page_title %}My Events{% endblock %}{% block content %}hello{% endblock %}'
PUBLIC_PAGE = '{% extends "base_public.html" %}{% block content %}hello{% endblock %}'

def render(source, user=None, path="/events/", **context):
    request = RequestFactory().get(path)
    request.user = user or AnonymousUser()
    return engines["django"].from_string(source).render(context, request)

@pytest.fixture
def admin_user():
    org = Organization.objects.create(name="Waco Regional")
    return User.objects.create_user("a@example.com", "pw", organization=org, is_admin=True)

@pytest.mark.urls("tests.future_urls")
def test_app_frame_has_top_bar_and_tab_bar(admin_user):
    html = render(APP_PAGE, admin_user)
    assert 'data-nav="top"' in html and 'data-nav="tabs"' in html and 'data-nav="more"' in html
    assert "hidden md:flex" in html and "md:hidden" in html
    assert "My Events" in html and "Tonight" in html and "hello" in html
    assert 'action="/logout/"' in html and 'method="post"' in html

@pytest.mark.urls("tests.future_urls")
def test_player_frame_has_no_more_tab():
    user = User.objects.create_user("p@example.com", "pw")
    html = render(APP_PAGE, user)
    assert 'data-nav="tabs"' in html and 'data-nav="more"' not in html
    assert "Standings" in html

@pytest.mark.urls("tests.future_urls")
def test_active_tab_marked(admin_user):
    request = RequestFactory().get("/events/")
    request.resolver_match = resolve("/events/")
    request.user = admin_user
    html = engines["django"].from_string(APP_PAGE).render({}, request)
    assert 'aria-current="page"' in html

def test_public_frame_has_no_navigation():
    html = render(PUBLIC_PAGE)
    assert "data-nav" not in html and "stryde-monogram.svg" in html and "hello" in html

def test_messages_render_as_toasts():
    html = render(PUBLIC_PAGE, messages=[Message(constants.SUCCESS, "Saved.")])
    toaster = html.split('id="toaster"', 1)[1]
    assert "Saved." in toaster and 'data-category="success"' in toaster

def test_404_page():
    response = Client().get("/no-such-page/")
    assert response.status_code == 404
    assert b"We couldn&#x27;t find that page." in response.content or b"We couldn't find that page." in response.content

@pytest.mark.urls("tests.error_urls")
def test_403_page():
    response = Client().get("/forbidden/")
    assert response.status_code == 403
    assert b"have access to this page." in response.content

@pytest.mark.urls("tests.error_urls")
def test_500_page():
    response = Client(raise_request_exception=False).get("/boom/")
    assert response.status_code == 500
    assert b"Something went wrong loading this page. Refresh to try again." in response.content
```

- [ ] **Step 3: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_layouts.py -v` FAIL.

- [ ] **Step 4: Implement the templates** as described above.

- [ ] **Step 5: Run tests** → `tests/test_layouts.py` PASS, then the full suite PASS.

- [ ] **Step 6: Commit**

```bash
git add templates tests/error_urls.py tests/test_layouts.py
git commit -m "feat(ui): app and public frames, toasts, and Stryde error pages"
```

---

### Task 4: P2 My Events and the My Games page

**Files:**
- Create: `league/urls.py`, `league/views.py`, `league/display.py`, `templates/league/event_list.html`, `templates/league/my_games.html`, `templates/components/empty_state.html`, `templates/components/status_badge.html`
- Modify: `config/urls.py` (`path("", include("league.urls"))`), `frontend/stryde.css` (`.data-table`)
- Test: `tests/test_my_events.py`

**Interfaces:**
- Consumes: `admin_required`, `player_for` (Task 2); `optional_reverse` (Task 2); `base_app.html` (Task 3).
- Produces:
  - `league/display.py`: `date_range(first: date | None, last: date | None) -> str`. It returns `""` when `first` is `None`; `"Mar 14"` when there's one date or both are the same; `"Mar 2–Mar 23"` (en dash) for a range in one year; `"Dec 29, 2026–Jan 19, 2027"` when the years differ.
  - `league.views.event_list`: path `events/`, name `event_list`, `admin_required`. Context `events` is a list of rows; each row is the `Event` annotated with `first_date` (Min of `weeks__date`), `last_date` (Max), `flight_count` (`Count("divisions__flights", distinct=True)`) and `link` (`optional_reverse("event_preview", pk)` for drafts, otherwise `optional_reverse("event_schedule", pk)`). The list is filtered to `request.user.organization`, and is empty when that is `None`. It's ordered by `Event.Meta.ordering`, newest first.
  - `league.views.my_games`: path `me/`, name `my_games`, `login_required`. Context `teams` is the `player_for(user)` teams whose event isn't a draft, with `select_related("flight__division__event")`. It's empty when there's no player.
  - `components/status_badge.html` takes `value` and `label`. It renders a pill `<span data-status="{{ value }}">` with these fills: `draft` → `bg-warn-bg text-warn`; `published` → `bg-progress text-ink`; `completed` → `bg-muted text-muted-foreground`. Later slices add account statuses to the same switch.
  - `components/empty_state.html` takes `icon`, `message`, `action_url`, `action_label`. It shows the button only when `action_url` is set. The button is `btn` (Coral, Indigo text) with a `plus` icon.

P2 page: the title is "My Events". The `+ Create` primary button shows only when `{% url 'event_create' as create_url %}` resolves. The table is `<table class="data-table">` with columns Name, Type, Dates, Flights, Status. Every `<td>` has `data-label="<column>"`. The row name is an `<a>` only when `row.link` is set. Below `md`, `.data-table` turns each row into a stacked card: no `<thead>`, and each cell shows its `data-label` through `td::before { content: attr(data-label) }`. The table sits in a `.card`. Empty state: icon `calendar-plus`, the PRD copy, and the create button if `create_url` is set.

My Games page (a first version; P11 in slice 7 fills it in): the title is "My Games". It shows one card per team with the team name in `font-display`, followed by "Event · Flight name" in muted text. Empty state: icon `trophy`, "You're not on any teams yet."

- [ ] **Step 1: Write the failing tests** in `tests/test_my_events.py`

```python
from datetime import date

import pytest

from accounts.models import Organization, User
from league.display import date_range
from league.models import Event
from tests.factories import add_flight, add_team, make_event

pytestmark = pytest.mark.django_db

def test_date_range():
    assert date_range(None, None) == ""
    assert date_range(date(2027, 3, 14), date(2027, 3, 14)) == "Mar 14"
    assert date_range(date(2027, 3, 2), date(2027, 3, 23)) == "Mar 2–Mar 23"
    assert date_range(date(2026, 12, 29), date(2027, 1, 19)) == "Dec 29, 2026–Jan 19, 2027"

@pytest.fixture
def league():
    event = make_event()                     # 4 weeks from 2027-03-02, org "Waco Regional"
    add_flight(event, format="mens")
    add_flight(event, format="mixed")
    return event

def admin_of(org, email="a@example.com"):
    return User.objects.create_user(email, "pw", organization=org, is_admin=True)

def test_events_table(client, league):
    Event.objects.create(organization=league.organization, name="Old Cup",
                                 type="tournament", start_date=date(2026, 9, 1), courts=2)
    Event.objects.create(organization=Organization.objects.create(name="Other"),
                         name="Not Mine", type="league", start_date=date(2027, 5, 1), courts=2)
    client.force_login(admin_of(league.organization))
    response = client.get("/events/")
    rows = response.context["events"]
    assert [r.name for r in rows] == ["Spring Tuesday League", "Old Cup"]
    assert rows[0].flight_count == 2                       # not multiplied by 4 weeks
    html = response.content.decode()
    assert "Mar 2–Mar 23" in html and 'data-label="Flights"' in html
    assert 'data-status="draft"' in html and "Not Mine" not in html
    assert f'href="/events/{league.pk}/' not in html      # no P4/P5 yet: plain-text rows

@pytest.mark.urls("tests.future_urls")
def test_rows_link_when_pages_exist(client, league):
    client.force_login(admin_of(league.organization))
    html = client.get("/events/").content.decode()
    assert f'href="/events/{league.pk}/preview/"' in html     # draft → P4
    assert 'href="/events/new/"' in html                      # Create button

def test_empty_state(client):
    client.force_login(admin_of(Organization.objects.create(name="Waco Regional")))
    assert "No events yet. Create your first league or tournament." in client.get("/events/").content.decode()

def test_admin_without_org_sees_empty_state(client):
    client.force_login(User.objects.create_superuser("root@example.com", "pw"))
    response = client.get("/events/")
    assert response.status_code == 200 and list(response.context["events"]) == []

def test_events_access(client, league):
    assert client.get("/events/").url.startswith("/login/?next=/events/")
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=league.organization))
    assert client.get("/events/").status_code == 403

def test_my_games_lists_published_teams_only(client, league):
    flight = league.divisions.get().flights.get(format="mens")
    team = add_team(flight, "Dinkers")
    player = team.players.first()
    player.email = "p@example.com"; player.save()
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=league.organization))
    assert "You're not on any teams yet." in client.get("/me/").content.decode()   # draft hidden
    league.status = Event.Status.PUBLISHED; league.save()
    html = client.get("/me/").content.decode()
    assert "Dinkers" in html and "Spring Tuesday League" in html
```

`test_events_access` checks the redirect prefix `/login/?next=`, so set `LOGIN_URL = "/login/"` in `config/settings.py` in this task. Use the path, not the URL name: `resolve_url` raises on a URL name that doesn't exist yet, and the `login` URL arrives in Task 5.

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_my_events.py -v` FAIL.

- [ ] **Step 3: Implement** `league/display.py`, the views, the URLs, the two components, the two page templates and the `.data-table` CSS, as specified above.

- [ ] **Step 4: Run tests** → `tests/test_my_events.py` PASS, then the full suite PASS. Then run `manage.py tailwind build` again so the new classes compile.

- [ ] **Step 5: Commit**

```bash
git add league config frontend templates tests/test_my_events.py
git commit -m "feat(league): My Events page and first My Games page"
```

---

### Task 5: Log in, log out, account and password reset

**Files:**
- Create: `accounts/urls.py`, `accounts/views.py`, `accounts/forms.py`, `templates/components/form_field.html`, `templates/registration/login.html`, `password_reset_form.html`, `password_reset_done.html`, `password_reset_confirm.html`, `password_reset_complete.html`, `password_reset_email.txt`, `password_reset_subject.txt`, `templates/accounts/account.html`
- Modify: `accounts/models.py` (`UserManager.get_by_natural_key`), `config/settings.py`, `config/urls.py` (`path("", include("accounts.urls"))`)
- Test: `tests/test_auth_pages.py`

**Interfaces:**
- Consumes: `role_of` (Task 2); `base_public.html` and `base_app.html` (Task 3); `event_list` and `my_games` (Task 4).
- Produces:
  - Settings: `LOGIN_URL = "/login/"` (already set in Task 4), `LOGIN_REDIRECT_URL = "home"`.
  - `accounts.views.home` (path `""`, name `home`): anonymous users go to `login`; admins and admin-players go to `event_list`; players go to `my_games`.
  - `LoginView` (`login/`) with `redirect_authenticated_user=True`, using `accounts.forms.EmailLoginForm`. That's `AuthenticationForm` with the username field labelled "Email" and `autocomplete="email"`.
  - `StrydeLogoutView(LogoutView)` (`logout/`, POST only): after logging out it adds `messages.info(request, "You're logged out.")` and redirects to `login`.
  - `AccountView(PasswordChangeView)` (`account/`, name `account`): it shows the user's email, the change-password form and a Log out form button. On success it redirects to `account` with `messages.success(…, "Your password was changed.")`.
  - Django's reset views under `password-reset/`, `password-reset/sent/`, `reset/<uidb64>/<token>/`, `reset/done/`, with their default names. The subject is "Reset your Stryde password". The email body is plain text and uses `{{ protocol }}://{{ domain }}{% url 'password_reset_confirm' uidb64=uid token=token %}`.
  - `UserManager.get_by_natural_key(email)`: a case-insensitive match (`email__iexact`). If there's more than one, it falls back to an exact match.
  - `components/form_field.html` takes `field`. It shows the label above the input, the widget, muted help text, and each error in `text-danger` under the field. Forms use Basecoat's `<form class="form">` so inputs pick up its styles.

Page copy: the login title is "Log in". The page has a "Forgot password?" link to `password_reset` and a primary "Log in" button. The reset title is "Reset your password", with the body "Enter your email and we'll send you a reset link.". The "sent" page says "If that email has an account, a reset link is on its way." and shows the same thing whether or not the email exists. The confirm page shows "This reset link has expired or was already used." when the token is invalid. The complete page says "Your password is set." with a "Log in" link.

- [ ] **Step 1: Write the failing tests** in `tests/test_auth_pages.py`

```python
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import Organization, User

pytestmark = pytest.mark.django_db

@pytest.fixture
def org():
    return Organization.objects.create(name="Waco Regional")

def test_login_page(client):
    html = client.get("/login/").content.decode()
    assert "Log in" in html and 'href="/password-reset/"' in html and "data-nav" not in html

def test_home_anonymous_goes_to_login(client):
    assert client.get("/").url == "/login/"

def test_admin_lands_on_events(client, org):
    User.objects.create_user("a@example.com", "pw-Str0ng-1", organization=org, is_admin=True)
    response = client.post("/login/", {"username": "a@example.com", "password": "pw-Str0ng-1"}, follow=True)
    assert response.redirect_chain[-1][0] == "/events/"

def test_player_lands_on_my_games(client, org):
    User.objects.create_user("p@example.com", "pw-Str0ng-1", organization=org)
    response = client.post("/login/", {"username": "p@example.com", "password": "pw-Str0ng-1"}, follow=True)
    assert response.redirect_chain[-1][0] == "/me/"

def test_login_ignores_email_case(client, org):
    User.objects.create_user("pat@example.com", "pw-Str0ng-1", organization=org)
    client.post("/login/", {"username": "PAT@Example.com", "password": "pw-Str0ng-1"})
    assert client.get("/").url == "/me/"

def test_wrong_password(client, org):
    User.objects.create_user("p@example.com", "pw-Str0ng-1", organization=org)
    response = client.post("/login/", {"username": "p@example.com", "password": "nope"})
    assert response.status_code == 200 and "correct email" in response.content.decode().lower()

def test_logged_in_user_skips_login(client, org):
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=org))
    assert client.get("/login/").status_code == 302

def test_logout(client, org):
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=org))
    assert client.get("/logout/").status_code == 405
    response = client.post("/logout/", follow=True)
    assert response.redirect_chain[-1][0] == "/login/"
    assert "You&#x27;re logged out." in response.content.decode() or "You're logged out." in response.content.decode()

def test_password_reset_email(client, org, mailoutbox):
    User.objects.create_user("p@example.com", "pw", organization=org)
    response = client.post("/password-reset/", {"email": "p@example.com"})
    assert response.url == "/password-reset/sent/"
    assert len(mailoutbox) == 1
    assert mailoutbox[0].subject == "Reset your Stryde password"
    assert "/reset/" in mailoutbox[0].body

def test_password_reset_unknown_email_looks_the_same(client, mailoutbox):
    response = client.post("/password-reset/", {"email": "nobody@example.com"})
    assert response.url == "/password-reset/sent/" and mailoutbox == []

def test_password_reset_confirm_sets_password(client, org):
    user = User.objects.create_user("p@example.com", "old", organization=org)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    response = client.get(f"/reset/{uid}/{default_token_generator.make_token(user)}/", follow=True)
    set_url = response.redirect_chain[-1][0]
    client.post(set_url, {"new_password1": "n3w-Str0ng-pw", "new_password2": "n3w-Str0ng-pw"})
    user.refresh_from_db()
    assert user.check_password("n3w-Str0ng-pw")

def test_account_changes_password(client, org):
    user = User.objects.create_user("p@example.com", "old-Str0ng-1", organization=org)
    client.force_login(user)
    assert 'action="/logout/"' in client.get("/account/").content.decode()
    response = client.post("/account/", {"old_password": "old-Str0ng-1",
        "new_password1": "n3w-Str0ng-pw", "new_password2": "n3w-Str0ng-pw"}, follow=True)
    assert "Your password was changed." in response.content.decode()
```

If `mailoutbox` stays empty because Django 6.1's `MAILERS` setting bypasses pytest-django's locmem override, override `MAILERS` in the test with `{"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}` through the `settings` fixture, and read `django.core.mail.outbox`. Don't change the project setting.

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_auth_pages.py -v` FAIL.

- [ ] **Step 3: Implement** the settings, URLs, views, form, manager override and templates as specified.

- [ ] **Step 4: Run tests** → `tests/test_auth_pages.py` PASS, then the full suite PASS (including `tests/test_accounts.py`).

- [ ] **Step 5: Commit**

```bash
git add accounts config templates tests/test_auth_pages.py
git commit -m "feat(accounts): Stryde login, logout, account and password reset pages"
```

---

### Task 6: Accept an invite

**Files:**
- Create: `accounts/invites.py`, `templates/accounts/invite_accept.html`
- Modify: `accounts/urls.py` (`invite/<str:token>/`, name `invite_accept`), `accounts/views.py`
- Test: `tests/test_invites.py`

**Interfaces:**
- Consumes: `league.models.Invite`, `Player`; `components/form_field.html` (Task 5); `home` (Task 5).
- Produces, `accounts/invites.py`:
  - `class InviteError(Exception)`, whose message is the user-facing text.
  - `ALREADY_USED = "This invite has already been used. Log in instead."`, `EXPIRED = "This invite link has expired. Ask your league admin to resend it."`, `HAS_ACCOUNT = "That email already has an account — log in instead."`
  - `check_invite(invite: Invite) -> None`: it raises `InviteError(ALREADY_USED)` if `accepted_at` is set, `InviteError(EXPIRED)` if `invite.is_expired()`, and `InviteError(HAS_ACCOUNT)` if a `User` with that email exists (case-insensitive). The checks run in that order.
  - `accept_invite(token: str, password: str) -> User`. It runs in `transaction.atomic()` and loads the invite with `select_for_update()` (raising `Invite.DoesNotExist` if unknown), then calls `check_invite`. It creates the user with `email=invite.email`, `organization=invite.organization` and `is_admin = invite.role == "admin"`. It links one player whose `user` is null: `invite.player` first, otherwise the first `Player` in the org whose email matches case-insensitively. Finally it sets `accepted_at = timezone.now()`.
- View `invite_accept`:
  - It returns 404 for an unknown token.
  - If `check_invite` raises, it renders the page with the error message and a "Log in" link, with no form.
  - Otherwise it shows "Join Stryde", the read-only email, and Django's `SetPasswordForm(user=User(email=invite.email))`, so the password validators check it against the email. The button is "Create account".
  - On a valid POST it calls `accept_invite(token, form.cleaned_data["new_password1"])`. If that raises `InviteError`, it re-renders with the message, which covers the race. On success it logs the new user in with `login(request, user, backend="django.contrib.auth.backends.ModelBackend")`, adds `messages.success(request, "Welcome to Stryde.")` and redirects to `home`.

- [ ] **Step 1: Write the failing tests** in `tests/test_invites.py`

```python
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.invites import ALREADY_USED, InviteError, accept_invite
from accounts.models import Organization, User
from league.models import Invite, Player

pytestmark = pytest.mark.django_db
PW = {"new_password1": "n3w-Str0ng-pw", "new_password2": "n3w-Str0ng-pw"}

@pytest.fixture
def org():
    return Organization.objects.create(name="Waco Regional")

@pytest.fixture
def player_invite(org):
    player = Player.objects.create(organization=org, name="Pat Lee", email="pat@example.com")
    return Invite.objects.create(organization=org, email="pat@example.com", role="player", player=player)

def test_invite_page_shows_email_and_form(client, player_invite):
    html = client.get(f"/invite/{player_invite.token}/").content.decode()
    assert "pat@example.com" in html and 'name="new_password1"' in html

def test_accept_player_invite(client, player_invite):
    response = client.post(f"/invite/{player_invite.token}/", PW, follow=True)
    assert response.redirect_chain[-1][0] == "/me/"
    user = User.objects.get(email="pat@example.com")
    assert user.organization == player_invite.organization and not user.is_admin
    assert Player.objects.get(name="Pat Lee").user == user
    player_invite.refresh_from_db()
    assert player_invite.accepted_at is not None

def test_accept_admin_invite_links_matching_player(client, org):
    Player.objects.create(organization=org, name="Ann", email="Ann@Example.com")
    invite = Invite.objects.create(organization=org, email="ann@example.com", role="admin")
    client.post(f"/invite/{invite.token}/", PW)
    user = User.objects.get(email="ann@example.com")
    assert user.is_admin and user.player.name == "Ann"
    assert client.get("/").url == "/events/"

def test_expired_invite(client, player_invite):
    player_invite.expires_at = timezone.now() - timedelta(minutes=1)
    player_invite.save()
    html = client.get(f"/invite/{player_invite.token}/").content.decode()
    assert "This invite link has expired. Ask your league admin to resend it." in html
    assert 'name="new_password1"' not in html

def test_unknown_token_404(client):
    assert client.get("/invite/not-a-token/").status_code == 404

def test_email_already_has_account_any_case(client, player_invite):
    User.objects.create_user("PAT@example.com", "pw")
    html = client.get(f"/invite/{player_invite.token}/").content.decode()
    assert "That email already has an account" in html

def test_weak_password_rejected(client, player_invite):
    response = client.post(f"/invite/{player_invite.token}/",
                           {"new_password1": "password", "new_password2": "password"})
    assert response.status_code == 200 and not User.objects.filter(email="pat@example.com").exists()

def test_accepting_twice_makes_one_user(client, player_invite):
    accept_invite(player_invite.token, "n3w-Str0ng-pw")
    with pytest.raises(InviteError, match=ALREADY_USED):
        accept_invite(player_invite.token, "n3w-Str0ng-pw")
    assert User.objects.filter(email__iexact="pat@example.com").count() == 1
    assert ALREADY_USED in client.post(f"/invite/{player_invite.token}/", PW).content.decode()

def test_player_linked_to_someone_else_is_not_taken(org, player_invite):
    other = User.objects.create_user("other@example.com", "pw", organization=org)
    player_invite.player.user = other
    player_invite.player.save()
    user = accept_invite(player_invite.token, "n3w-Str0ng-pw")
    assert Player.objects.get(name="Pat Lee").user == other
    assert not Player.objects.filter(user=user).exists()
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_invites.py -v` FAIL.

- [ ] **Step 3: Implement** `accounts/invites.py`, the view, the URL and `templates/accounts/invite_accept.html` (on `base_public.html`) as specified.

- [ ] **Step 4: Run tests** → `tests/test_invites.py` PASS, then the full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add accounts templates tests/test_invites.py
git commit -m "feat(accounts): accept an invite, set a password, and link the player"
```

---

### Task 7: Demo player login, README, and the screen check

**Files:**
- Modify: `league/management/commands/seed_demo.py`, `tests/test_seed.py`, `README.md`

**Interfaces:**
- Consumes: everything above.
- Produces in `seed_demo`:
  - `PLAYER_EMAIL = "player@example.com"`, password `ADMIN_PASSWORD` (`"pickleball"`).
  - The shared Intermediate player (on both Men's and Mixed) gets that email and a linked non-admin `User` in the demo org.
  - The league is set to `published` after generation; the tournament stays `draft`, so P2 shows both statuses.
  - `--reset` deletes the player login as well as the admin.
  - The final message names both logins and `/login/` instead of `/admin/`.

- [ ] **Step 1: Write the failing tests** (add to `tests/test_seed.py`, following the file's existing `call_command` style)

```python
def test_seed_creates_player_login_on_two_flights():
    call_command("seed_demo")
    user = User.objects.get(email="player@example.com")
    assert not user.is_admin and user.check_password("pickleball")
    assert user.player.teams.count() == 2

def test_seed_league_published_tournament_draft():
    call_command("seed_demo")
    assert Event.objects.get(name="Spring Tuesday League").status == "published"
    assert Event.objects.get(name="March Madness Shootout").status == "draft"

def test_seed_reset_removes_player_login_first():
    call_command("seed_demo")
    call_command("seed_demo", "--reset")
    assert User.objects.filter(email="player@example.com").count() == 1
```

- [ ] **Step 2: Run to verify they fail** → `.venv/Scripts/python -m pytest tests/test_seed.py -v` (the new tests FAIL).

- [ ] **Step 3: Implement** the seed changes. Then update `README.md`:
  - Setup now installs `django-tailwind-cli==4.8.3`.
  - Dev server: `.venv/Scripts/python manage.py tailwind runserver`, which runs Django and the CSS watcher. Production CSS: `manage.py tailwind build`.
  - The app is at `http://127.0.0.1:8000/`.
  - Demo logins: `admin@example.com` and `player@example.com`, both with `pickleball`.
  - `static/css/stryde.css` is built, not committed.

- [ ] **Step 4: Run the full suite** → `.venv/Scripts/python -m pytest` all PASS.

- [ ] **Step 5: Screen check at 390px and 1280px**

Run `manage.py tailwind build`, `manage.py migrate`, `manage.py seed_demo --reset`, then `manage.py runserver`. In a browser tool (Playwright or Claude in Chrome), at widths 390 and 1280, capture these screens:
- `/login/`
- `/events/` as admin (both rows, Published and Draft badges)
- `/events/` empty: create a second admin with no events through `/admin/`, or log in as a superuser with no organization
- `/me/` as the player
- `/account/`
- a 404 page

On each screen, confirm:
- `document.documentElement.scrollWidth <= window.innerWidth` (no sideways scroll).
- The tab bar shows at 390 and the top bar at 1280.
- The Inter and Montserrat fonts load (check the Network panel: no Google requests, and the woff2 files are 200).
- Coral buttons have Indigo text.

Save the screenshots in the session scratchpad, not the repo. Fix anything off and re-run the suite.

- [ ] **Step 6: Commit**

```bash
git add league/management/commands/seed_demo.py tests/test_seed.py README.md
git commit -m "feat(league): demo player login and published demo league; README for the front end"
```
