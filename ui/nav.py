"""The app's navigation per role (spec §5.2).

Items point at URL names. An item whose page isn't built yet (its name doesn't
reverse) is left out, so later slices only add their URL to make it appear.
"""
from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse

from accounts.roles import role_of


@dataclass(frozen=True)
class NavLink:
    label: str
    url: str
    icon: str
    active: bool


@dataclass(frozen=True)
class Nav:
    top: list[NavLink]
    tabs: list[NavLink]
    more: list[NavLink]
    account: NavLink | None


def optional_reverse(name: str, *args) -> str | None:
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        return None


# (label, URL name, icon)
MY_EVENTS = ("My Events", "event_list", "calendar-days")
EVENTS = ("Events", "event_list", "calendar-days")
TONIGHT = ("Tonight", "tonight", "moon")
PLAYERS = ("Players", "player_list", "users")
ADMINS = ("Admins", "admin_list", "shield")
MY_GAMES = ("My Games", "my_games", "trophy")
STANDINGS = ("Standings", "my_standings", "chart-column")
ACCOUNT = ("Account", "account", "user-round")

ITEMS = {
    "admin": {
        "top": [MY_EVENTS, PLAYERS, ADMINS],
        "tabs": [EVENTS, TONIGHT, PLAYERS],
        "more": [ADMINS, ACCOUNT],
    },
    "admin_player": {
        "top": [MY_EVENTS, MY_GAMES, PLAYERS, ADMINS],
        "tabs": [EVENTS, TONIGHT, MY_GAMES],
        "more": [PLAYERS, ADMINS, ACCOUNT],
    },
    "player": {
        "top": [MY_GAMES],
        "tabs": [MY_GAMES, STANDINGS, ACCOUNT],
        "more": [],
    },
}


def _links(items, current_url_name):
    links = []
    for label, name, icon in items:
        url = optional_reverse(name)
        if url is not None:
            links.append(NavLink(label, url, icon, active=name == current_url_name))
    return links


def nav_for(user, current_url_name: str | None) -> Nav:
    items = ITEMS[role_of(user)]
    account = _links([ACCOUNT], current_url_name)
    return Nav(
        top=_links(items["top"], current_url_name),
        tabs=_links(items["tabs"], current_url_name),
        more=_links(items["more"], current_url_name),
        account=account[0] if account else None,
    )
