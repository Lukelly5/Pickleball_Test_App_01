from collections.abc import Sequence
from dataclasses import dataclass, replace

from scheduler.generate import generate
from scheduler.types import Flight, ScheduleError


@dataclass(frozen=True)
class FitResult:
    games: int
    rounds: int
    courts: int
    minutes: int
    window_minutes: int
    fits: bool
    rounds_that_fit: int
    suggested_games_per_team: int | None


def _rounds_needed(flights: Sequence[Flight], courts: int) -> tuple[int, int]:
    schedule = generate(flights, courts)
    rounds = max((m.round_no for m in schedule.matches), default=0)
    return len(schedule.matches), rounds


def check_fit(
    flights: Sequence[Flight], courts: int, game_minutes: int, window_minutes: int
) -> FitResult:
    if game_minutes < 1:
        raise ScheduleError("Game length must be at least 1 minute.")
    if window_minutes < 1:
        raise ScheduleError("The time window must be at least 1 minute.")
    for flight in flights:
        if len(flight.games_per_team_by_week) != 1:
            raise ScheduleError(
                f"A tournament flight has exactly one week; "
                f"flight {flight.name} has {len(flight.games_per_team_by_week)}."
            )

    games, rounds = _rounds_needed(flights, courts)
    rounds_that_fit = window_minutes // game_minutes
    fits = rounds <= rounds_that_fit

    suggestion = None
    if not fits:
        largest = max(f.games_per_team_by_week[0] for f in flights)
        for cap in range(largest - 1, 0, -1):
            capped = [
                replace(f, games_per_team_by_week=(min(f.games_per_team_by_week[0], cap),))
                for f in flights
            ]
            if _rounds_needed(capped, courts)[1] <= rounds_that_fit:
                suggestion = cap
                break

    return FitResult(
        games=games,
        rounds=rounds,
        courts=courts,
        minutes=rounds * game_minutes,
        window_minutes=window_minutes,
        fits=fits,
        rounds_that_fit=rounds_that_fit,
        suggested_games_per_team=suggestion,
    )


def _duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


def _window(minutes: int) -> str:
    if minutes > 60 and minutes % 60 == 0:
        return f"{minutes // 60}-hour"
    return f"{minutes}-minute"


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}" if n == 1 else f"{n} {thing}s"


def fit_message(result: FitResult) -> str:
    games = _count(result.games, "game")
    rounds = _count(result.rounds, "round")
    courts = _count(result.courts, "court")
    if result.fits:
        return (
            f"{games} · {rounds} on {courts} · "
            f"about {_duration(result.minutes)}. "
            f"Fits your {_window(result.window_minutes)} window."
        )
    if result.rounds_that_fit == 0:
        advice = "Extend the window."
    elif result.suggested_games_per_team is None:
        advice = "Add courts or extend the window."
    else:
        advice = (
            "Add courts, extend the window, or lower games per team to "
            f"{result.suggested_games_per_team}."
        )
    need = "needs" if result.games == 1 else "need"
    return (
        f"{games} {need} {rounds} on {courts} "
        f"(~{_duration(result.minutes)}). Your {_window(result.window_minutes)} window "
        f"fits {_count(result.rounds_that_fit, 'round')}. {advice}"
    )
