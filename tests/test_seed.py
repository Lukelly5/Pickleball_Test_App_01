import pytest
from django.core.management import call_command
from django.db.models import Count

from accounts.models import User
from league.models import Event, Flight, Match, Player

pytestmark = pytest.mark.django_db


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
    call_command("seed_demo")
    call_command("seed_demo")
    assert "Demo data already exists. Use --reset to rebuild it." in capsys.readouterr().out
    assert Match.objects.count() == 140


def test_seed_reset_rebuilds():
    call_command("seed_demo")
    call_command("seed_demo", "--reset")
    assert Event.objects.count() == 2 and Match.objects.count() == 140 and User.objects.count() == 1
