"""Division and Flight filters read from the query string, shared by the
Schedule Preview and the Schedule tab."""

from django.http import QueryDict

from league.models import Division, Event, Flight

LEVEL_LABELS = dict(Division.Level.choices)


def to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_filters(event: Event, params: QueryDict) -> tuple[str, int | None]:
    """(division level or "", flight pk or None); junk values fall back."""
    levels = set(Division.objects.filter(event=event).values_list("level", flat=True))
    division = params.get("division", "")
    if division not in levels:
        division = ""

    flights = Flight.objects.filter(division__event=event)
    if division:
        flights = flights.filter(division__level=division)
    flight = to_int(params.get("flight"))
    if flight not in set(flights.values_list("pk", flat=True)):
        flight = None
    return division, flight


def filter_options(
    event: Event, division: str
) -> tuple[list[tuple[str, str]], list[tuple[int, str]]]:
    """(divisions as (level, label), flights as (pk, name) narrowed to division)."""
    divisions = [
        (d.level, LEVEL_LABELS[d.level]) for d in Division.objects.filter(event=event).order_by("pk")
    ]
    rows = Flight.objects.filter(division__event=event).select_related("division")
    if division:
        rows = rows.filter(division__level=division)
    rows = rows.order_by("division__pk", "pk")
    return divisions, [(f.pk, f.name) for f in rows]
