"""The real URLconf plus a stand-in for every URL name a later slice will build.

Tests swap this in with @pytest.mark.urls("tests.future_urls") to see the nav and
page links as they will look once every page exists.
"""
from django.http import HttpResponse
from django.urls import NoReverseMatch, path, reverse

from config import urls as real

FUTURE = [
    ("events/", "event_list", ()),
    ("events/new/", "event_create", ()),
    ("events/<int:pk>/preview/", "event_preview", (1,)),
    ("events/<int:pk>/schedule/", "event_schedule", (1,)),
    ("tonight/", "tonight", ()),
    ("standings/", "my_standings", ()),
    ("players/", "player_list", ()),
    ("admins/", "admin_list", ()),
    ("me/", "my_games", ()),
    ("account/", "account", ()),
    ("login/", "login", ()),
    ("logout/", "logout", ()),
]


def stand_in(request, **kwargs):
    return HttpResponse("stand-in")


def _exists(name, args):
    try:
        reverse(name, args=args, urlconf=real)
    except NoReverseMatch:
        return False
    return True


urlpatterns = list(real.urlpatterns) + [
    path(route, stand_in, name=name) for route, name, args in FUTURE if not _exists(name, args)
]
