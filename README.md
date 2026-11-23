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

## Demo data

`seed_demo` creates the organization "Waco Regional (Demo)" with a 6-flight league and an 8-team tournament, and two logins at `/login/`, both with the password `pickleball`:

- `admin@example.com` - the organization admin.
- `player@example.com` - a player on two flights (Men's and Mixed) of the league.

The league is published and the tournament is a draft.

- `seed_demo --reset` deletes the demo organization and both logins, then rebuilds them. Other organizations are never touched.
- `seed_demo` refuses to run when DEBUG is off; add `--force` to run it anyway.

## Styles

The front end uses Tailwind (through `django-tailwind-cli`) with the Stryde theme in `frontend/stryde.css`. The compiled file, `static/css/stryde.css`, is built, not committed: run `tailwind runserver` or `tailwind build` after a fresh checkout.

## Environment variables

- `DJANGO_SECRET_KEY` - the secret key.
- `DJANGO_DEBUG` - `1` (the default) turns DEBUG on; anything else turns it off.
- `DJANGO_ALLOWED_HOSTS` - comma-separated allowed hosts (default `localhost,127.0.0.1`).

The development defaults (an insecure secret key and DEBUG on) must be overridden before any real deployment.
