from django.contrib import admin

from league.models import (
    Division,
    Event,
    Flight,
    GameScore,
    Invite,
    Match,
    Player,
    Team,
    TeamMember,
    Week,
)


class DivisionInline(admin.TabularInline):
    model = Division
    extra = 0


class WeekInline(admin.TabularInline):
    model = Week
    extra = 0


class TeamInline(admin.TabularInline):
    model = Team
    extra = 0


class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    min_num = 2
    max_num = 2
    validate_min = True
    validate_max = True
    autocomplete_fields = ["player"]


class GameScoreInline(admin.TabularInline):
    model = GameScore
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "status", "start_date", "courts")
    list_filter = ("type", "status")
    inlines = [DivisionInline, WeekInline]


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "event", "level")


@admin.register(Flight)
class FlightAdmin(admin.ModelAdmin):
    list_display = ("__str__", "division", "games_per_team_by_week")
    inlines = [TeamInline]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "flight", "withdrawn_at")
    inlines = [TeamMemberInline]


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    search_fields = ("name", "email")
    list_display = ("name", "email", "organization", "user")


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "organization", "created_at", "expires_at", "accepted_at")


@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ("__str__", "event", "number", "date", "status")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("week", "round_no", "court_no", "flight", "team_a", "team_b", "status")
    list_filter = ("status", "flight__division__event")
    inlines = [GameScoreInline]
