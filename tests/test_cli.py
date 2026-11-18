import pytest
from scheduler.cli import main

def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err

def test_T1_from_the_command_line(capsys):
    code, out, _ = run(capsys, "league", "--teams", "4", "--weeks", "4",
                       "--games-per-team", "2", "--courts", "2")
    assert code == 0
    assert out.count("Week ") == 4 and "Round 2" in out and "Round 3" not in out
    assert "Total: 16 games · 8 per team · every pair meets 2–3 times" in out

def test_per_week_list_and_preset(capsys):
    code, out, _ = run(capsys, "league", "--teams", "10", "--weeks", "2",
                       "--games-per-team", "1,2", "--courts", "5")
    assert code == 0 and "Total: 15 games" in out
    code, out, _ = run(capsys, "league", "--teams", "4", "--weeks", "3",
                       "--preset", "once", "--courts", "2")
    assert code == 0 and "every pair meets 1 times" not in out and "meets once" in out

def test_tournament_prints_fit_message(capsys):
    code, out, _ = run(capsys, "tournament", "--teams", "8", "--courts", "4",
                       "--game-minutes", "15", "--window", "60")
    assert code == 0 and "lower games per team to 4." in out

def test_file_input_keeps_shared_player_apart(capsys):
    code, out, _ = run(capsys, "league", "--file", "examples/two_flights.json")
    assert code == 0 and "Round 2" in out

@pytest.mark.parametrize("argv", [
    ["league", "--teams", "1", "--weeks", "2", "--games-per-team", "1", "--courts", "2"],
    ["league", "--teams", "4", "--weeks", "2", "--games-per-team", "1", "--courts", "0"],
    ["league", "--teams", "4", "--weeks", "3", "--games-per-team", "1,2", "--courts", "2"],
    ["league", "--teams", "4", "--weeks", "4", "--preset", "once", "--courts", "2"],
    ["league", "--teams", "four", "--weeks", "2", "--games-per-team", "1", "--courts", "2"],
    ["league", "--file", "does-not-exist.json"],
])
def test_bad_input_is_a_message_not_a_traceback(capsys, argv):
    try:
        code = main(argv)
    except SystemExit as e:      # argparse exits by itself for unparseable values
        code = e.code
    err = capsys.readouterr().err
    assert code == 2 and err.strip() and "Traceback" not in err


@pytest.mark.parametrize("text", [
    "{not json",
    '{"flights": []}',
    '{"courts": 2, "flights": [{"name": "A", "games_per_team": [1], "teams": [{"name": "X", "players": ["Pat"]}]}]}',
    '{"courts": "2", "flights": []}',
    '[]',
])
def test_malformed_file_is_one_error_line(capsys, tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    code = main(["league", "--file", str(path)])
    err = capsys.readouterr().err
    assert code == 2 and err.startswith("error: ") and err.count("\n") == 1

def test_file_uses_team_names_and_flight_prefix(capsys):
    code, out, _ = run(capsys, "league", "--file", "examples/two_flights.json")
    assert "Int Men's: Dinkers v" in out
    assert "Total (Int Men's):" in out and "Total (Int Mixed):" in out
