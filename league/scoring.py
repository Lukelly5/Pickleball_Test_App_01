"""Score rules for a match: which game rows show, who won each game, what
messages apply, the result line, and whether a player or admin may save.

Pure Python with no HTTP and no model imports; the live check and the save
both go through `check_score`.
"""

import re
from dataclasses import dataclass

_BEST_OF = {"single": 1, "best_of_3": 3, "best_of_5": 5}
_NUMBER = re.compile(r"\d{1,2}")


@dataclass(frozen=True)
class Format:
    best_of: int
    points_to_win: int
    win_by_two: bool

    @classmethod
    def of(cls, event) -> "Format":
        return cls(_BEST_OF[event.match_format], event.points_to_win, event.win_by_two)

    @property
    def label(self) -> str:
        length = "1 game" if self.best_of == 1 else f"Best of {self.best_of}"
        return f"{length} · games to {self.points_to_win} · win by {2 if self.win_by_two else 1}"


@dataclass(frozen=True)
class Message:
    text: str
    blocking: bool


@dataclass(frozen=True)
class ScoreCheck:
    shown: int
    values: tuple
    game_winners: tuple
    wins: tuple
    leader: str | None
    messages: tuple
    result: str
    _games: tuple = ()

    @property
    def can_save(self) -> bool:
        return not any(m.blocking for m in self.messages)

    @property
    def save_anyway(self) -> bool:
        return self.can_save and bool(self.messages)

    def games_to_save(self) -> list[tuple[int, int]]:
        return list(self._games)


def raw_games(data, best_of: int) -> list[tuple[str, str]]:
    return [(data.get(f"g{n}a", ""), data.get(f"g{n}b", "")) for n in range(1, best_of + 1)]


def _parse(value: str):
    """Return an int, None for blank, or False for junk."""
    if value == "":
        return None
    return int(value) if _NUMBER.fullmatch(value) else False


def _winner(pair):
    a, b = pair
    return "a" if a > b else "b" if a < b else None


def _shown_rows(fmt: Format, winners: list) -> int:
    """How many rows to show, given the winner (or None) of each row so far."""
    if fmt.best_of == 1:
        return 1
    if fmt.best_of == 3:
        return 3 if winners[0] and winners[1] and winners[0] != winners[1] else 2
    a = sum(1 for w in winners[:3] if w == "a")
    b = sum(1 for w in winners[:3] if w == "b")
    if not all(winners[:3]) or max(a, b) == 3:
        return 3
    if not winners[3]:
        return 4
    a += winners[3] == "a"
    b += winners[3] == "b"
    return 5 if a == b == 2 else 4


def _points_message(fmt: Format, n: int, w: int, l: int) -> str | None:
    t = fmt.points_to_win
    if w == l:
        return f"Game {n}: A game can't end in a tie — {w}–{l}."
    w, l = max(w, l), min(w, l)
    if w < t:
        return f"Game {n}: Games to {t} end when a team reaches {t} — {w}–{l} isn't a final score."
    if fmt.win_by_two:
        if not ((w == t and l <= t - 2) or (w > t and w - l == 2)):
            return f"Game {n}: Games to {t} must be won by 2 — {w}–{l} isn't a final score."
    elif w > t:
        return f"Game {n}: Games to {t} end at {t} — {w}–{l} isn't a final score."
    return None


def check_score(fmt: Format, raw: list[tuple[str, str]], names: tuple[str, str], *, admin: bool) -> ScoreCheck:
    values = tuple((a.strip(), b.strip()) for a, b in raw)
    parsed = [(_parse(a), _parse(b)) for a, b in values]

    # Row state: "junk", "blank", "half" or "filled".
    states = []
    for a, b in parsed:
        if a is False or b is False:
            states.append("junk")
        elif a is None and b is None:
            states.append("blank")
        elif a is None or b is None:
            states.append("half")
        else:
            states.append("filled")
    winners = [_winner(p) if s == "filled" else None for p, s in zip(parsed, states)]

    shown = _shown_rows(fmt, winners)
    states, parsed, winners = states[:shown], parsed[:shown], winners[:shown]
    wins = (winners.count("a"), winners.count("b"))
    leader = "a" if wins[0] > wins[1] else "b" if wins[1] > wins[0] else None

    messages = []
    last_filled = max((i for i, s in enumerate(states) if s == "filled"), default=-1)
    for i, state in enumerate(states):
        n = i + 1
        if state == "junk":
            messages.append(Message(f"Game {n}: scores must be whole numbers from 0 to 99.", True))
        elif state == "half" or (state == "blank" and i < last_filled):
            messages.append(Message(f"Game {n}: enter both scores.", True))
        elif state == "filled":
            text = _points_message(fmt, n, *parsed[i])
            if text:
                tie = winners[i] is None
                messages.append(Message(text, tie or not admin))
    if not admin:
        for i in range(last_filled + 1, shown):
            if states[i] == "blank":
                messages.append(Message(f"Game {i + 1}: enter both scores.", True))
                break

    clinch = fmt.best_of // 2 + 1
    if leader is None:
        messages.append(Message("Enter games until one team is ahead.", True))
    elif fmt.best_of > 1 and max(wins) < clinch:
        messages.append(Message(
            f"A best-of-{fmt.best_of} match ends when one team wins {clinch} games.", not admin))

    result = ""
    if leader:
        name = names[0] if leader == "a" else names[1]
        if fmt.best_of == 1:
            score = f"{max(parsed[0])}–{min(parsed[0])}"
        else:
            score = f"{max(wins)}–{min(wins)}"
        result = f"{name} win {score}"

    return ScoreCheck(
        shown=shown,
        values=values,
        game_winners=tuple(winners),
        wins=wins,
        leader=leader,
        messages=tuple(messages),
        result=result,
        _games=tuple(p for p, s in zip(parsed, states) if s == "filled"),
    )
