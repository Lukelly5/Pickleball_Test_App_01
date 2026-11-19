# Pickleball League Manager

## Setup

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install "django>=6.1,<6.2" "pytest-django>=4.14"
```

## Common commands

```powershell
.venv/Scripts/python manage.py migrate            # create the database
.venv/Scripts/python manage.py createsuperuser    # log in with an email address
.venv/Scripts/python manage.py seed_demo          # demo data (added in Task 5)
.venv/Scripts/python manage.py runserver          # http://127.0.0.1:8000/admin/
.venv/Scripts/python -m pytest                    # run the tests
.venv/Scripts/python -m scheduler --help          # the scheduling engine CLI
```
