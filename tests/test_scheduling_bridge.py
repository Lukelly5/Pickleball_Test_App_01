import pytest

from league.models import Event, GameScore, Match, Team, TeamMember
from league.scheduling import event_flights, generate_event, load_schedule
from scheduler import ScheduleError
from tests.factories import add_flight, add_player, add_team, make_event

pytestmark = pytest.mark.django_db


def t1_event():  # PRD T1: 4 teams, 4 weeks, 2 games/team/week, 2 courts
    event = make_event(weeks=4, courts=2)
    flight = add_flight(event, games=[2, 2, 2, 2])
    for n in ["Dinkers", "Smashers", "Lobsters", "Kitchen Kings"]:
        add_team(flight, n)
    return event


def event_matches(event):
    return Match.objects.filter(flight__division__event=event)


def test_t1_through_database():
    event = t1_event()
    generate_event(event)
    matches = event_matches(event)
    assert matches.count() == 16
    for week in event.weeks.all():
        assert {m.round_no for m in matches.filter(week=week)} == {1, 2}
        assert all(m.court_no in (1, 2) for m in matches.filter(week=week))


def test_regenerating_replaces_matches():
    event = t1_event()
    generate_event(event)
    generate_event(event)
    assert event_matches(event).count() == 16


def test_regenerate_blocked_once_a_score_exists():
    event = t1_event()
    generate_event(event)
    m = Match.objects.first()
    GameScore.objects.create(match=m, game_no=1, points_a=11, points_b=7)
    with pytest.raises(ScheduleError, match="Scores have been entered"):
        generate_event(event)
    assert event_matches(event).count() == 16


def test_regenerate_blocked_by_final_match_or_forfeit():
    event = t1_event()
    generate_event(event)
    m = Match.objects.first()
    m.status = Match.Status.FINAL
    m.save()
    with pytest.raises(ScheduleError, match="Scores have been entered"):
        generate_event(event)
    m.status = Match.Status.SCHEDULED
    m.forfeited_by = m.team_a
    m.save()
    with pytest.raises(ScheduleError, match="Scores have been entered"):
        generate_event(event)


def test_regenerate_allowed_after_publish_without_scores():
    event = t1_event()
    generate_event(event)
    event.status = Event.Status.PUBLISHED
    event.save()
    generate_event(event)
    event.refresh_from_db()
    assert event_matches(event).count() == 16
    assert event.status == Event.Status.PUBLISHED


def test_t5_player_on_mens_and_mixed_never_double_booked():
    event = make_event(weeks=1, courts=4)
    org = event.organization
    mens = add_flight(event, format="mens", games=[2])
    mixed = add_flight(event, format="mixed", games=[2])
    pat = add_player(org, "Pat Lee")
    add_team(mens, "Dinkers", (pat, add_player(org, "Max")))
    for n in ["Smashers", "Lobsters", "Kitchen Kings"]:
        add_team(mens, n)
    add_team(mixed, "Volley Llamas", (pat, add_player(org, "Ana")))
    for n in ["Net Ninjas", "Drop Shots", "Third Shots"]:
        add_team(mixed, n)
    generate_event(event)
    pat_teams = TeamMember.objects.filter(player=pat).values_list("team_id", flat=True)
    pat_rounds = [
        m.round_no
        for m in Match.objects.all()
        if m.team_a_id in pat_teams or m.team_b_id in pat_teams
    ]
    assert len(pat_rounds) == 4 and len(set(pat_rounds)) == 4


def test_two_different_players_with_same_name_are_not_one_person():
    event = make_event(weeks=1, courts=4)
    org = event.organization
    mens = add_flight(event, format="mens", games=[2])
    mixed = add_flight(event, format="mixed", games=[2])
    pat1 = add_player(org, "Pat Lee")
    pat2 = add_player(org, "Pat Lee")
    add_team(mens, "Dinkers", (pat1, add_player(org, "Max")))
    add_team(mens, "Smashers")
    add_team(mixed, "Volley Llamas", (pat2, add_player(org, "Ana")))
    add_team(mixed, "Net Ninjas")
    generate_event(event)
    keys = {p for f in event_flights(event) for t in f.teams for p in t.players}
    assert f"Pat Lee (#{pat1.pk})" in keys
    assert f"Pat Lee (#{pat2.pk})" in keys
    assert "Pat Lee" not in keys


def test_team_with_one_player_is_rejected():
    event = t1_event()
    team = Team.objects.get(name="Dinkers")
    team.members.last().delete()
    with pytest.raises(ScheduleError, match="Dinkers needs exactly 2 players before generating."):
        generate_event(event)


def test_withdrawn_team_is_left_out_of_generation():
    from django.utils import timezone

    event = make_event(weeks=4, courts=2)
    flight = add_flight(event, games=[2, 2, 2, 2])
    for n in ["Dinkers", "Smashers", "Lobsters", "Kitchen Kings", "Out Team"]:
        add_team(flight, n)
    out = Team.objects.get(name="Out Team")
    out.withdrawn_at = timezone.now()
    out.save()
    generate_event(event)
    matches = event_matches(event)
    assert matches.count() == 16
    assert not matches.filter(team_a=out).exists()
    assert not matches.filter(team_b=out).exists()


def test_withdrawn_team_with_wrong_member_count_is_ignored():
    from django.utils import timezone

    event = t1_event()
    flight = event.divisions.get().flights.get()
    ghost = Team.objects.create(flight=flight, name="Ghost", withdrawn_at=timezone.now())
    generate_event(event)
    assert not event_matches(event).filter(team_a=ghost).exists()


def test_week_count_mismatch_names_the_flight():
    event = t1_event()
    event.set_week_count(3)
    with pytest.raises(
        ScheduleError, match="Intermediate Men's has games for 4 weeks but the event has 3."
    ):
        generate_event(event)


def test_no_flights():
    event = make_event()
    with pytest.raises(ScheduleError, match="Add at least one flight before generating."):
        generate_event(event)


def test_fewer_than_two_teams_message_passes_through():
    event = make_event()
    flight = add_flight(event)
    add_team(flight, "Dinkers")
    with pytest.raises(
        ScheduleError, match="Add at least 2 teams to Intermediate Men's before generating."
    ):
        generate_event(event)


def test_load_schedule_round_trips():
    event = t1_event()
    generated = generate_event(event)
    loaded, flights = load_schedule(event)
    assert loaded == generated and [f.name for f in flights] == ["Intermediate Men's"]


def test_generation_is_deterministic():
    event = t1_event()
    first = generate_event(event)
    assert generate_event(event) == first


def test_admin_generate_action(admin_client):
    event = t1_event()
    r = admin_client.post(
        "/admin/league/event/",
        {"action": "generate_schedule", "_selected_action": [event.pk]},
        follow=True,
    )
    assert b"Generated 16 games for Spring Tuesday League." in r.content


def test_admin_generate_action_shows_errors(admin_client):
    event = make_event()  # no flights
    r = admin_client.post(
        "/admin/league/event/",
        {"action": "generate_schedule", "_selected_action": [event.pk]},
        follow=True,
    )
    assert b"Spring Tuesday League: Add at least one flight before generating." in r.content
