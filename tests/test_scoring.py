import pytest
from django.http import QueryDict

from league.scoring import Format, check_score, raw_games

B1 = Format(1, 11, True)
B3 = Format(3, 11, True)
B5 = Format(5, 11, True)
NAMES = ("Dinkers", "Smashers")


def chk(fmt, *pairs, admin=False):
    raw = list(pairs) + [("", "")] * (fmt.best_of - len(pairs))
    return check_score(fmt, raw, NAMES, admin=admin)


@pytest.mark.parametrize("t,wb2,a,b,ok", [
    (11, True, 11, 9, True), (11, True, 11, 10, False), (11, True, 13, 11, True), (11, True, 14, 11, False),
    (11, True, 12, 11, False), (11, True, 9, 7, False), (11, False, 11, 10, True), (11, False, 12, 11, False),
    (15, True, 15, 13, True), (21, True, 21, 19, True), (21, True, 20, 18, False), (11, True, 0, 11, True),
])
def test_single_game_rule(t, wb2, a, b, ok):
    assert chk(Format(1, t, wb2), (str(a), str(b))).can_save is ok


def test_messages_verbatim():
    assert chk(B1, ("11", "10")).messages[0].text == "Game 1: Games to 11 must be won by 2 — 11–10 isn't a final score."
    assert chk(B1, ("9", "9")).messages[0].text == "Game 1: A game can't end in a tie — 9–9."
    assert chk(B1, ("9", "7")).messages[0].text == "Game 1: Games to 11 end when a team reaches 11 — 9–7 isn't a final score."
    assert chk(Format(1, 11, False), ("12", "10")).messages[0].text == "Game 1: Games to 11 end at 11 — 12–10 isn't a final score."


def test_rows_best_of_3():
    assert chk(B3).shown == 2
    assert chk(B3, ("11", "7"), ("7", "11")).shown == 3
    assert chk(B3, ("11", "7"), ("11", "5")).shown == 2


def test_rows_best_of_5():
    assert chk(B5).shown == 3
    assert chk(B5, ("11", "7"), ("11", "7"), ("7", "11")).shown == 4
    assert chk(B5, ("11", "7"), ("11", "7"), ("11", "7")).shown == 3
    assert chk(B5, ("11", "7"), ("11", "7"), ("7", "11"), ("7", "11")).shown == 5
    assert chk(B5, ("11", "7"), ("11", "7"), ("11", "7"), ("7", "11")).shown == 3
    assert chk(B5, ("11", "7"), ("11", "7"), ("7", "11"), ("11", "7")).shown == 4


def test_hidden_row_ignored():
    c = chk(B3, ("11", "7"), ("11", "5"), ("11", "3"))
    assert c.shown == 2 and c.games_to_save() == [(11, 7), (11, 5)] and c.result == "Dinkers win 2–0"


def test_result_lines():
    assert chk(B1, ("7", "11")).result == "Smashers win 11–7"
    assert chk(B3, ("11", "7"), ("9", "11"), ("11", "5")).result == "Dinkers win 2–1"


def test_game_winners_for_teal():
    assert chk(B3, ("11", "7"), ("9", "11")).game_winners == ("a", "b", None)


def test_player_trailing_blank_blocked():
    c = chk(B3, ("11", "7"))
    assert not c.can_save and "Game 2: enter both scores." in [m.text for m in c.messages]


def test_admin_saves_one_nil():  # owner's decision
    c = chk(B3, ("11", "7"), admin=True)
    assert c.can_save and c.save_anyway and c.games_to_save() == [(11, 7)]
    assert [m.text for m in c.messages] == ["A best-of-3 match ends when one team wins 2 games."]
    assert c.result == "Dinkers win 1–0"


def test_admin_timed_game_warning():
    c = chk(B1, ("9", "7"), admin=True)
    assert c.can_save and c.save_anyway


def test_tie_blocks_admin():
    assert not chk(B1, ("9", "9"), admin=True).can_save


def test_no_leader_blocks_admin():
    c = chk(B3, ("11", "7"), ("7", "11"), admin=True)
    assert not c.can_save and c.messages[-1].text == "Enter games until one team is ahead."


def test_all_blank_blocks_admin():
    assert not chk(B3, admin=True).can_save


def test_half_filled_blocks_admin():
    assert "Game 1: enter both scores." in [m.text for m in chk(B3, ("11", ""), admin=True).messages]


def test_blank_before_filled_blocks_admin():
    assert not chk(B3, ("", ""), ("11", "5"), admin=True).can_save


def test_best_of_5_not_decided_text():
    c = chk(B5, ("11", "7"), ("11", "7"), ("7", "11"), admin=True)
    assert "A best-of-5 match ends when one team wins 3 games." in [m.text for m in c.messages]


def test_best_of_1_never_not_decided():
    assert chk(B1, ("11", "7")).messages == ()


@pytest.mark.parametrize("junk", ["abc", "-3", "100", "11.5", "1e1", "١١"])
def test_junk_input(junk):  # Review Focus 1
    c = chk(B1, (junk, "7"), admin=True)
    assert not c.can_save and c.messages[0].text == "Game 1: scores must be whole numbers from 0 to 99."


def test_spaces_trimmed():
    assert chk(B1, (" 11 ", "7")).can_save


def test_format_label():
    assert Format(3, 11, True).label == "Best of 3 · games to 11 · win by 2"
    assert Format(1, 15, False).label == "1 game · games to 15 · win by 1"


def test_format_of_event():
    class E:
        match_format, points_to_win, win_by_two = "best_of_5", 21, False

    assert Format.of(E()) == Format(5, 21, False)


def test_raw_games_reads_fields():
    assert raw_games(QueryDict("g1a=11&g1b=7"), 3) == [("11", "7"), ("", ""), ("", "")]
