from datetime import date

from accounts.models import Organization, User
from league.models import Division, Event, Flight, GameScore, Player, Team, TeamMember


def make_event(name="Spring Tuesday League", weeks=4, courts=2, **fields):
    org, _ = Organization.objects.get_or_create(name="Waco Regional")
    event = Event.objects.create(
        organization=org,
        name=name,
        start_date=date(2027, 3, 2),
        courts=courts,
        **fields,
    )
    event.set_week_count(weeks)
    return event


def add_player(org, name, email=""):
    return Player.objects.create(organization=org, name=name, email=email)


def add_flight(event, level="intermediate", format="mens", games=(2, 2, 2, 2)):
    division, _ = Division.objects.get_or_create(event=event, level=level)
    return Flight.objects.create(
        division=division, format=format, games_per_team_by_week=list(games)
    )


def add_team(flight, name, players=None):
    org = flight.event.organization
    if players is None:
        players = (add_player(org, f"{name} A"), add_player(org, f"{name} B"))
    team = Team.objects.create(flight=flight, name=name)
    for player in players:
        TeamMember.objects.create(team=team, player=player)
    return team


def admin_of(org, email="a@example.com"):
    return User.objects.create_user(email, "pw", organization=org, is_admin=True)


def score(match, points_a=11, points_b=5, game_no=1):
    return GameScore.objects.create(
        match=match, game_no=game_no, points_a=points_a, points_b=points_b
    )
