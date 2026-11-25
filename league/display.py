"""Small text helpers for showing league data on pages."""
from datetime import date


def _day(d: date, with_year: bool = False) -> str:
    text = f"{d:%b} {d.day}"
    return f"{text}, {d.year}" if with_year else text


def date_range(first: date | None, last: date | None) -> str:
    """'Mar 2–Mar 23'; one day as 'Mar 14'; years shown only when they differ."""
    if first is None:
        return ""
    if last is None or last == first:
        return _day(first)
    with_year = first.year != last.year
    return f"{_day(first, with_year)}–{_day(last, with_year)}"


def short_day(d: date) -> str:
    """'Tue Dec 2'."""
    return f"{d:%a} {d:%b} {d.day}"
