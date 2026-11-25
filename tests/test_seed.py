import pytest
from django.core.management import call_command
from django.db.models import Count

from django.core.management.base import CommandError

from accounts.models import Organization, User
from league.models import Event, Flight, Match, Player
from tests.factories import make_event

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def debug_on(settings):
    settings.DEBUG = True  # the test runner turns it off


def test_seed_creates_demo():
    call_command("seed_demo")
    assert Event.objects.count() == 2 and Flight.objects.count() == 7 and Match.objects.count() == 140
    assert User.objects.get(email="admin@example.com").check_password("pickleball")
    assert Organization.objects.get().name == "Waco Regional (Demo)"
    league = Event.objects.get(name="Spring Tuesday League")
    league_counts = [f.teams.count() for f in Flight.objects.filter(division__event=league).order_by("division__pk", "pk")]
    assert league_counts == [4, 4, 5, 5, 6, 6]
    tournament = Event.objects.get(name="March Madness Shootout")
    assert [f.teams.count() for f in Flight.objects.filter(division__event=tournament)] == [8]


def test_seed_league_has_a_player_on_two_flights_each_division():
    call_command("seed_demo")
    league = Event.objects.get(name="Spring Tuesday League")
    for division in league.divisions.all():
        assert Player.objects.filter(teams__flight__division=division).annotate(n=Count("teams")).filter(n=2).exists()


def test_seed_twice_does_not_duplicate(capsys):
    call_command("seed_demo")
    call_command("seed_demo")
    assert "Demo data already exists. Use --reset to rebuild it." in capsys.readouterr().out
    assert Match.objects.count() == 140


def test_seed_reset_rebuilds():
    call_command("seed_demo")
    call_command("seed_demo", "--reset")
    assert Event.objects.count() == 2 and Match.objects.count() == 140 and User.objects.count() == 2


def test_seed_does_not_touch_a_real_organization():
    real = make_event(name="Real Event")
    assert real.organization.name == "Waco Regional"
    call_command("seed_demo", "--reset")
    assert Organization.objects.filter(name="Waco Regional").exists()
    assert Event.objects.filter(name="Real Event").exists()
    call_command("seed_demo", "--reset")
    assert Event.objects.filter(name="Real Event").exists()


def test_seed_refuses_without_debug(settings, capsys):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo")
    assert "seed_demo only runs with DEBUG on. Use --force to run it anyway." in capsys.readouterr().err
    assert Event.objects.count() == 0


def test_seed_force_runs_without_debug(settings):
    settings.DEBUG = False
    call_command("seed_demo", "--force")
    assert Event.objects.count() == 2


def test_seed_adopts_existing_admin_user():
    User.objects.create_user("admin@example.com", "old")
    call_command("seed_demo")
    user = User.objects.get(email="admin@example.com")
    assert user.check_password("pickleball")
    assert user.is_admin and user.is_staff and user.is_superuser
    assert user.organization.name == "Waco Regional (Demo)"


def test_seed_creates_player_login_on_two_flights():
    call_command("seed_demo")
    user = User.objects.get(email="player@example.com")
    assert not user.is_admin and user.check_password("pickleball")
    assert user.player.teams.count() == 2
    assert user.organization.name == "Waco Regional (Demo)"


def test_seed_league_published_tournament_draft():
    call_command("seed_demo")
    assert Event.objects.get(name="Spring Tuesday League").status == "published"
    assert Event.objects.get(name="March Madness Shootout").status == "draft"


def test_seed_reset_removes_player_login_first():
    call_command("seed_demo")
    call_command("seed_demo", "--reset")
    assert User.objects.filter(email="player@example.com").count() == 1


def test_seed_league_has_share_token():
    call_command("seed_demo")
    assert Event.objects.get(name="Spring Tuesday League").share_token
    assert Event.objects.get(name="March Madness Shootout").share_token is None
