from scheduler.fairness import FairnessReport, fairness_report, pair_meet_text, summary_line
from scheduler.fit import FitResult, check_fit, fit_message
from scheduler.generate import generate
from scheduler.pairings import round_robin_preset
from scheduler.swap import SwapConflict, move_game, swap_games, swap_teams
from scheduler.types import Flight, Match, Schedule, ScheduleError, Team

__all__ = [
    "check_fit",
    "fit_message",
    "FitResult",
    "generate",
    "move_game",
    "pair_meet_text",
    "fairness_report",
    "FairnessReport",
    "Flight",
    "Match",
    "round_robin_preset",
    "Schedule",
    "ScheduleError",
    "summary_line",
    "SwapConflict",
    "swap_games",
    "swap_teams",
    "Team",
]
