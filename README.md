# Pickleball League Manager

## Setup

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install "django>=6.1,<6.2" "django-tailwind-cli==4.8.3" "pytest-django>=4.14"
```

## Common commands

```powershell
.venv/Scripts/python manage.py migrate            # create the database
.venv/Scripts/python manage.py createsuperuser    # log in with an email address
.venv/Scripts/python manage.py seed_demo          # demo data (see below)
.venv/Scripts/python manage.py tailwind runserver # Django + the CSS watcher, http://127.0.0.1:8000/
.venv/Scripts/python manage.py tailwind build     # build the production CSS once
.venv/Scripts/python -m pytest                    # run the tests
.venv/Scripts/python -m scheduler --help          # the scheduling engine CLI
```

## Create a league

Admins create a league at `/events/new/` (the "Create" button on My Events). It is a five-step wizard: Basics, Scoring, Flights, Teams, Games plan.

- Each step saves a draft as you go, so you can leave and resume from `/events/<id>/setup/`, which opens the first unfinished step.
- Generate (on the last step) saves a draft schedule and opens the Schedule Preview.
- Setup locks once any score is entered: weeks, courts, scoring, flights, teams and the games plan can no longer change. Only the name and player score entry stay editable.

## Review and publish a schedule

After Generate, the schedule opens at `/events/<id>/preview/` (My Events links to it too). Use the week tabs and the Division and Flight filters to look through it.

- Swap two games, swap two teams, or move a game into an open court: click one tile, then click another. A clash (a team on two courts in the same round, a move to another week, a scored or withdrawn game) is refused with a message and nothing changes.
- The fairness panel under the grid shows games per team, season totals, repeat pairings and the longest sit for the week.
- Regenerate replaces every game, including your swaps and moves. It asks first and is refused once a score has been entered.
- Publish asks first and is blocked while the setup inputs have changed since the schedule was made ("Regenerate first").
- A published league can still be edited in setup. The wizard shows warnings: renames show up right away, removing a team or flight removes its games immediately, and other changes apply when you regenerate.

## Event page and share link

Publishing opens the event page at `/events/<id>/schedule/`, with Schedule, Standings, Teams and Settings tabs (Standings and Teams are "Coming soon" for now).

- Schedule shows one week at a time as game cards, with week pills and Division and Flight filters. A card marks your own team with "You" and lists who is sitting out.
- Tonight (`/tonight/`, or the Tonight button) shows tonight's games for every flight in a phone-first layout. When there are none, it names the next game night.
- Settings has the share link. Anyone with it can see the schedule, standings and teams at `/s/<token>/` with no login. Copy it, or Reset it to retire the old link. Share pages have no app navigation and are marked noindex.
- My Games links each team to its flight's schedule.

## Enter scores

Each card on the Schedule and Tonight views has an "Enter score" button (or "Edit score" once scored). It opens a score sheet that fills the screen on a phone. Games are validated against the league's format (best of 1, 3 or 5, points to win, win by 2), and the sheet shows the result live; later games (Game 3, or Games 4-5 in best of 5) appear only when needed.

- Who can score: an admin can score any match. A player can score a match only when the event is published, player score entry is on in the league setup, they are on one of the two teams, and the game night is today or earlier (or the week has no date). A player's score that breaks the format is blocked; an admin sees a warning and can "Save anyway".
- Once an admin has scored or edited a match, a player's later save is refused with "An admin has already scored this match."
- Forfeit: an admin picks the team that forfeited, and the other team wins. Players cannot forfeit.
- Clear: an admin can clear a score or forfeit after confirming, which returns the match to unscored. A cleared match stays locked to players; only an admin can enter it again.
- Cards show the game chips and "Last edited by" the last person to change the score.
- Locking: once any match has a score or forfeit, the league's setup is locked and Regenerate on the Preview is refused, so scores are never orphaned.
- Without JavaScript the same pages work as plain forms and redirect back to the schedule week.

## Demo data

`seed_demo` creates the organization "Waco Regional (Demo)" with a 6-flight league and an 8-team tournament, and two logins at `/login/`, both with the password `pickleball`:

- `admin@example.com` - the organization admin.
- `player@example.com` - a player on two flights (Men's and Mixed) of the league.

The league is published, with a share link on its Settings tab, and the tournament is a draft.

- `seed_demo --tonight` re-dates the league so Week 2 is today (Week 1 a week earlier, Weeks 3 and 4 a week and two weeks later), which makes the Tonight view show games. It works on a fresh seed, with `--reset`, or on an existing demo, and leaves the tournament alone.
- `seed_demo --reset` deletes the demo organization and both logins, then rebuilds them. Other organizations are never touched.
- `seed_demo` refuses to run when DEBUG is off; add `--force` to run it anyway.

## Styles

The front end uses Tailwind (through `django-tailwind-cli`) with the Stryde theme in `frontend/stryde.css`. The compiled file, `static/css/stryde.css`, is built, not committed: run `tailwind runserver` or `tailwind build` after a fresh checkout.

## Environment variables

- `DJANGO_SECRET_KEY` - the secret key.
- `DJANGO_DEBUG` - `1` (the default) turns DEBUG on; anything else turns it off.
- `DJANGO_ALLOWED_HOSTS` - comma-separated allowed hosts (default `localhost,127.0.0.1`).

The development defaults (an insecure secret key and DEBUG on) must be overridden before any real deployment.
