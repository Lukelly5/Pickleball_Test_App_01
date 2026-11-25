import pytest

from tests.test_score_views import (  # noqa: F401  (fixtures and helpers)
    TIE_BREAK_11_10,
    WIN,
    card_html,
    fresh,
    league,
    m2,
    schedule,
    score_url,
    user_on,
)

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}


def test_sheet_partial(client, league, m2):
    html = client.get(score_url(m2), **HX).content.decode()
    assert "<html" not in html
    assert 'id="score-form"' in html
    assert f"Wk 2 · R{m2.round_no} · Court {m2.court_no}" in html
    assert 'id="score-g2a"' in html
    assert 'id="score-g3a"' not in html


def test_check_shows_game_3(client, league, m2):
    r = client.post(score_url(m2, "check/"), {"g1a": "11", "g1b": "7", "g2a": "7", "g2b": "11"}, **HX)
    html = r.content.decode()
    assert 'id="score-g3a"' in html
    assert "<html" not in html
    assert 'id="score-body"' in html


def test_check_result_and_teal(client, league, m2):
    r = client.post(score_url(m2, "check/"), {"g1a": "11", "g1b": "7", "g2a": "11", "g2b": "5"}, **HX)
    html = r.content.decode()
    assert f"{m2.team_a.name} win 2–0" in html
    assert "bg-progress" in html


def test_check_player_message_and_disabled(client, league, m2):
    client.force_login(user_on(m2.team_a))
    r = client.post(score_url(m2, "check/"), {"g1a": "11", "g1b": "10"}, **HX)
    html = r.content.decode()
    assert "must be won by 2" in html
    save = html.split("Save score")[0].rsplit("<button", 1)[1]
    assert "disabled" in save


def test_htmx_save_returns_oob_card(client, league, m2):
    r = client.post(score_url(m2), WIN, **HX)
    body = r.content.decode()
    assert r.status_code == 200
    assert r["HX-Trigger"] == "score-saved"
    assert "hx-swap-oob" in body and f'data-card="{m2.pk}"' in body
    assert "Edit score" in body
    assert "Score saved" in body
    assert fresh(m2).status == "final"


def test_htmx_save_blocked_stays_in_sheet(client, league, m2):
    client.force_login(user_on(m2.team_a))
    r = client.post(score_url(m2), TIE_BREAK_11_10, **HX)
    assert not r.has_header("HX-Trigger")
    assert 'id="score-body"' in r.content.decode()


def test_htmx_forfeit_and_clear_oob(client, league, m2):
    r = client.post(score_url(m2, "forfeit/"), {"team": m2.team_a_id}, **HX)
    assert r["HX-Trigger"] == "score-saved"
    assert f'data-card="{m2.pk}"' in r.content.decode()
    r = client.post(score_url(m2, "clear/"), {"confirm": "1"}, **HX)
    assert r["HX-Trigger"] == "score-saved"
    assert "Enter score" in r.content.decode()


def test_card_button_has_hx_and_href(client, league, m2):
    card = card_html(schedule(client, league), m2)
    assert f'href="{score_url(m2)}"' in card
    assert f'hx-get="{score_url(m2)}"' in card
    assert 'hx-target="#score-sheet"' in card


def test_dialog_on_app_page_not_share(client, league, m2):
    assert 'id="score-sheet"' in schedule(client, league)
    token = league.share_token
    html = client.get(f"/s/{token}/schedule/?week=2").content.decode()
    assert 'id="score-sheet"' not in html


def test_vary_header(client, league, m2):
    assert "HX-Request" in client.get(score_url(m2))["Vary"]


def test_card_open_guarded_on_success(client, league, m2):
    card = card_html(schedule(client, league), m2)
    assert "event.detail.successful" in card and "showModal" in card
    assert card.index("event.detail.successful") < card.index("showModal")


def test_live_form_serializes_requests(client, league, m2):
    html = client.get(score_url(m2), **HX).content.decode()
    form = html.split('id="score-form"')[1].split(">")[0]
    assert 'hx-sync="this:queue last"' in form
    inputs = [chunk.split(">")[0] for chunk in html.split("<input")[1:] if "score-g" in chunk.split(">")[0]]
    assert inputs and all('hx-sync="closest form:queue last"' in i for i in inputs)


def test_check_response_preserves_inputs_but_sheet_load_does_not(client, league, m2):
    check = client.post(score_url(m2, "check/"), {"g1a": "11", "g1b": "7"}, **HX).content.decode()
    inputs = [chunk.split(">")[0] for chunk in check.split("<input")[1:] if "score-g" in chunk.split(">")[0]]
    assert inputs and all("hx-preserve" in i for i in inputs)
    sheet = client.get(score_url(m2), **HX).content.decode()
    assert "hx-preserve" not in sheet


def test_winner_highlight_is_on_wrapper_not_input(client, league, m2):
    r = client.post(score_url(m2, "check/"), {"g1a": "11", "g1b": "7"}, **HX).content.decode()
    inp = r.split('id="score-g1a"')[1].split(">")[0]
    assert "bg-progress" not in inp
