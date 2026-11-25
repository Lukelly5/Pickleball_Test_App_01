from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization, User
from league.models import Division, Event, Flight, Player, Team, TeamMember
from league.scheduling import generate_event

ORG_NAME = "Waco Regional (Demo)"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "pickleball"
PLAYER_EMAIL = "player@example.com"
LEAGUE_NAME = "Spring Tuesday League"

FIRST_NAMES = [
    "Alex", "Blake", "Casey", "Drew", "Emery", "Finn", "Gray", "Harper", "Indy", "Jordan",
    "Kai", "Logan", "Morgan", "Nico", "Owen", "Parker", "Quinn", "Riley", "Sam", "Taylor",
]
LAST_NAMES = [
    "Adams", "Brooks", "Carter", "Diaz", "Ellis", "Foster", "Grant", "Hayes", "Ingram", "Jensen",
    "Keller", "Lopez", "Mercer", "Nolan", "Ortiz", "Patel", "Reed", "Shaw", "Turner", "Vega",
]
TEAM_NAMES = [
    "Dink Dynasty", "Kitchen Crashers", "Net Ninjas", "Paddle Pals",
    "Smash Brothers", "Lob Squad", "Drop Shot Dream", "Baseline Bandits",
]

# (level, men's teams, mixed teams)
LEAGUE_DIVISIONS = [
    (Division.Level.BEGINNER, 4, 4),
    (Division.Level.INTERMEDIATE, 5, 5),
    (Division.Level.ADVANCED, 6, 6),
]


class Command(BaseCommand):
    help = "Create demo data: a 6-flight league and an 8-team tournament."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="Delete the demo data first and rebuild it."
        )
        parser.add_argument(
            "--force", action="store_true", help="Run even when DEBUG is off."
        )
        parser.add_argument(
            "--tonight",
            action="store_true",
            help="Re-date the league so Week 2 is today.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            self.stderr.write("seed_demo only runs with DEBUG on. Use --force to run it anyway.")
            raise CommandError("seed_demo refused to run with DEBUG off.")
        with transaction.atomic():
            existing = Organization.objects.filter(name=ORG_NAME)
            if existing.exists():
                if not options["reset"]:
                    if options["tonight"]:
                        self._redate_league(Event.objects.get(organization__name=ORG_NAME, name=LEAGUE_NAME))
                        self.stdout.write("Demo league re-dated: Week 2 is tonight.")
                    else:
                        self.stdout.write("Demo data already exists. Use --reset to rebuild it.")
                    return
                existing.delete()
                User.objects.filter(email__in=[ADMIN_EMAIL, PLAYER_EMAIL]).delete()
            self._seed()
            if options["tonight"]:
                self._redate_league(Event.objects.get(organization__name=ORG_NAME, name=LEAGUE_NAME))

    def _redate_league(self, league):
        """Date the weeks so Week 2 is today; the league starts a week earlier."""
        today = timezone.localdate()
        for week in league.weeks.all():
            week.date = today + timedelta(days=7 * (week.number - 2))
            week.save(update_fields=["date"])
        league.start_date = today - timedelta(days=7)
        league.save(update_fields=["start_date"])

    def _seed(self):
        org = Organization.objects.create(name=ORG_NAME)
        flags = {"organization": org, "is_admin": True, "is_staff": True, "is_superuser": True}
        admin = User.objects.filter(email=ADMIN_EMAIL).first()
        if admin is None:
            User.objects.create_user(ADMIN_EMAIL, ADMIN_PASSWORD, **flags)
        else:
            for field, value in flags.items():
                setattr(admin, field, value)
            admin.set_password(ADMIN_PASSWORD)
            admin.save()
        self._player_count = 0
        self._org = org

        league = Event.objects.create(
            organization=org,
            name=LEAGUE_NAME,
            type=Event.Type.LEAGUE,
            start_date=date(2027, 3, 2),
            courts=6,
            setup_step=5,
        )
        league.set_week_count(4)
        for level, mens, mixed in LEAGUE_DIVISIONS:
            division = Division.objects.create(event=league, level=level)
            mens_players = self._flight(division, Flight.Format.MENS, mens, [2, 2, 2, 2])
            # One man also plays Mixed, so the demo shows a player on two flights.
            shared = mens_players[0]
            self._flight(division, Flight.Format.MIXED, mixed, [2, 2, 2, 2], reuse=[shared])
            if level == Division.Level.INTERMEDIATE:
                self._player_login(shared)

        tournament = Event.objects.create(
            organization=org,
            name="March Madness Shootout",
            type=Event.Type.TOURNAMENT,
            start_date=date(2027, 3, 13),
            courts=4,
            window_minutes=120,
            game_minutes=15,
            setup_step=5,
        )
        tournament.set_week_count(1)
        division = Division.objects.create(event=tournament, level=Division.Level.INTERMEDIATE)
        self._flight(division, Flight.Format.MIXED, 8, [7])

        games = sum(len(generate_event(e).matches) for e in (league, tournament))
        # The league is published so the player login has games to see; the tournament stays a draft.
        league.status = Event.Status.PUBLISHED
        league.save(update_fields=["status"])
        league.ensure_share_token()
        self.stdout.write(
            f"Seeded 2 events, 7 flights, {games} games. Log in at /login/ as "
            f"{ADMIN_EMAIL} (admin) or {PLAYER_EMAIL} (player), password {ADMIN_PASSWORD}"
        )

    def _player_login(self, player):
        """Give one demo player (on two flights) an email and a player login."""
        player.email = PLAYER_EMAIL
        user = User.objects.filter(email=PLAYER_EMAIL).first()
        if user is None:
            user = User.objects.create_user(PLAYER_EMAIL, ADMIN_PASSWORD, organization=self._org)
        else:
            user.organization = self._org
            user.is_admin = user.is_staff = user.is_superuser = False
            user.set_password(ADMIN_PASSWORD)
            user.save()
        player.user = user
        player.save(update_fields=["email", "user"])

    def _new_player(self):
        i = self._player_count
        self._player_count += 1
        name = f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {LAST_NAMES[(i // len(FIRST_NAMES)) % len(LAST_NAMES)]}"
        return Player.objects.create(organization=self._org, name=name)

    def _flight(self, division, fmt, team_count, games, reuse=()):
        """Create a flight of two-player teams; returns every player used."""
        flight = Flight.objects.create(
            division=division, format=fmt, games_per_team_by_week=games
        )
        reuse = list(reuse)
        used = []
        for n in range(team_count):
            team = Team.objects.create(flight=flight, name=TEAM_NAMES[n])
            for _ in range(2):
                player = reuse.pop(0) if reuse else self._new_player()
                TeamMember.objects.create(team=team, player=player)
                used.append(player)
        return used
