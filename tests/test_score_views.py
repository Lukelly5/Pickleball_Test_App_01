from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Organization, User
from league.models import Event, Match, Player, Team, Week
from league.scheduling import generate_event
from tests.factories import add_flight, add_team, admin_of, make_event

pytestmark = pytest.mark.django_db

NAMES = ("Dinkers", "Smashers", "Lobsters", "Kings")
WIN = {"g1a": "11", "g1b": "7", "g2a": "11", "g2b": "5"}
TIE_BREAK_11_10 = {"g1a": "11", "g1b": "10", "g2a": "11", "g2b": "5"}
WARN = {"g1a": "9", "g1b": "7", "g2a": "11", "g2b": "5"}


@pytest.fixture
def league(client):
    event = make_event(
        weeks=4,
        courts=3,
        status=Event.Status.PUBLISHED,
        match_format="best_of_3",
        player_score_entry=True,
    )
    flight = add_flight(event, games=(2, 2, 2, 2))
    for n in NAMES:
        add_team(flight, n)
    generate_event(event)
    today = timezone.localdate()
    for week in event.weeks.all():
        Week.objects.filter(pk=week.pk).update(date=today + timedelta(days=7 * (week.number - 2)))
    client.force_login(admin_of(event.organization))
    return event


@pytest.fixture
def m2(league):
    return Match.objects.filter(flight__division__event=league, week__number=2).order_by("round_no", "court_no").first()


def score_url(m, tail=""):
    return f"/events/{m.flight.division.event_id}/matches/{m.pk}/score/{tail}"


def schedule(client, event, week=2):
    return client.get(f"/events/{event.pk}/schedule/?week={week}").content.decode()


def user_on(team, email="p@example.com"):
    player = team.players.first()
    user = User.objects.create_user(email, "pw", organization=team.flight.division.event.organization)
    Player.objects.filter(pk=player.pk).update(user=user)
    return user


def card_html(html, m):
    return html.split(f'data-card="{m.pk}"')[1].split("</article>")[0]


def fresh(m):
    return Match.objects.get(pk=m.pk)


def test_card_has_enter_score_for_admin(client, league, m2):
    html = schedule(client, league)
    assert f'href="{score_url(m2)}"' in html
    assert "Enter score" in card_html(html, m2)


def test_card_no_button_for_other_player(client, league, m2):
    other = next(t for t in Team.objects.filter(flight__division__event=league) if t not in (m2.team_a, m2.team_b))
    client.force_login(user_on(other))
    html = schedule(client, league)
    assert f'href="{score_url(m2)}"' not in card_html(html, m2)


def test_share_page_has_no_score_button(client, league, m2):
    token = league.ensure_share_token()
    html = client.get(f"/s/{token}/schedule/?week=2").content.decode()
    assert "/matches/" not in html
    assert "Enter score" not in html


def test_form_shows_format_and_rows(client, league, m2):
    r = client.get(score_url(m2))
    assert r.status_code == 200
    html = r.content.decode()
    assert "Best of 3 · games to 11 · win by 2" in html
    for n in (1, 2, 3):
        for side in "ab":
            assert f'id="score-g{n}{side}"' in html
    assert 'inputmode="numeric"' in html


def test_save_redirects_to_week(client, league, m2):
    r = client.post(score_url(m2), WIN)
    assert r.status_code == 302
    assert r["Location"].endswith("?week=2")
    assert "Score saved" in client.get(r["Location"]).content.decode()
    m = fresh(m2)
    assert m.status == "final" and m.winner_id == m.team_a_id


def test_save_blocked_rerenders(client, league, m2):
    client.force_login(user_on(m2.team_a))
    r = client.post(score_url(m2), TIE_BREAK_11_10)
    assert r.status_code == 200
    html = r.content.decode()
    assert "Game 1: Games to 11 must be won by 2 — 11–10 isn&#x27;t a final score." in html or (
        "Game 1: Games to 11 must be won by 2 — 11–10 isn't a final score." in html
    )
    assert fresh(m2).status == "scheduled"
    assert m2.games.count() == 0


def test_admin_save_anyway_two_taps(client, league, m2):
    r = client.post(score_url(m2), WARN)
    assert r.status_code == 200
    html = r.content.decode()
    assert "Save anyway" in html
    assert "Best of 3 match" not in html
    assert fresh(m2).status == "scheduled"
    r = client.post(score_url(m2), {**WARN, "anyway": "1"})
    assert r.status_code == 302
    assert fresh(m2).status == "final"


def test_card_after_save(client, league, m2):
    client.post(score_url(m2), WIN)
    card = card_html(schedule(client, league), m2)
    assert "Last edited by" in card
    assert "Edit score" in card
    assert ">11<" in card and ">7<" in card


def test_forfeit_flow(client, league, m2):
    assert "Which team forfeited?" in client.get(score_url(m2, "forfeit/")).content.decode()
    r = client.post(score_url(m2, "forfeit/"), {"team": m2.team_b_id})
    assert r.status_code == 302 and r["Location"].endswith("?week=2")
    html = client.get(r["Location"]).content.decode()
    assert "Forfeit saved" in html
    assert f"Forfeit · {m2.team_a.name} wins" in card_html(html, m2)


def test_forfeit_junk_team_rerenders(client, league, m2):
    r = client.post(score_url(m2, "forfeit/"), {"team": "abc"})
    assert r.status_code == 200
    assert "Choose the team that forfeited." in r.content.decode()
    assert fresh(m2).status == "scheduled"


def test_clear_confirm(client, league, m2):
    client.post(score_url(m2), WIN)
    r = client.post(score_url(m2, "clear/"), {})
    assert r.status_code == 200
    assert "Clear the score for" in r.content.decode()
    assert fresh(m2).status == "final"
    r = client.post(score_url(m2, "clear/"), {"confirm": "1"})
    assert r.status_code == 302
    assert "Score cleared" in client.get(r["Location"]).content.decode()
    m = fresh(m2)
    assert m.status == "scheduled" and m.games.count() == 0


def test_player_forfeit_and_clear_403(client, league, m2):
    client.force_login(user_on(m2.team_a))
    assert client.get(score_url(m2, "forfeit/")).status_code == 403
    assert client.post(score_url(m2, "forfeit/"), {"team": m2.team_a_id}).status_code == 403
    assert client.get(score_url(m2, "clear/")).status_code == 403
    assert client.post(score_url(m2, "clear/"), {"confirm": "1"}).status_code == 403


def test_other_org_404(client, league, m2):
    other = Organization.objects.create(name="Elsewhere")
    client.force_login(admin_of(other, "x@example.com"))
    assert client.get(score_url(m2)).status_code == 404


def test_same_org_non_member_403(client, league, m2):
    other = next(t for t in Team.objects.filter(flight__division__event=league) if t not in (m2.team_a, m2.team_b))
    client.force_login(user_on(other))
    assert client.get(score_url(m2)).status_code == 403
    assert client.post(score_url(m2), WIN).status_code == 403


def test_match_from_other_event_404(client, league, m2):
    event2 = make_event(name="Other", status=Event.Status.PUBLISHED, match_format="best_of_3")
    flight = add_flight(event2)
    for n in NAMES:
        add_team(flight, n)
    generate_event(event2)
    foreign = Match.objects.filter(flight__division__event=event2).first()
    url = f"/events/{league.pk}/matches/{foreign.pk}/score/"
    assert client.get(url).status_code == 404
    assert client.post(url, WIN).status_code == 404
    assert fresh(foreign).status == "scheduled"


def test_draft_event_redirects_admin_to_preview(client, league, m2):
    Event.objects.filter(pk=league.pk).update(status=Event.Status.DRAFT)
    r = client.get(score_url(m2))
    assert r.status_code == 302 and "preview" in r["Location"]


def test_cancelled_week_403(client, league, m2):
    Week.objects.filter(pk=m2.week_id).update(status=Week.Status.CANCELLED)
    assert client.get(score_url(m2)).status_code == 403


def test_anonymous_redirects_to_login(client, league, m2):
    client.logout()
    r = client.get(score_url(m2))
    assert r.status_code == 302 and "login" in r["Location"]


def test_player_late_save_after_admin_lock_shows_refusal(client, league, m2):
    player = user_on(m2.team_a)
    client.post(score_url(m2), WIN)
    client.force_login(player)
    r = client.post(score_url(m2), {"g1a": "11", "g1b": "3", "g2a": "11", "g2b": "3"})
    assert r.status_code == 200
    assert "An admin has already scored this match." in r.content.decode().replace("&#x27;", "'")
    assert sorted(m2.games.values_list("points_a", "points_b")) == [(11, 5), (11, 7)]
