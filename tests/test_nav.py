import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory

from accounts.models import Organization, User
from accounts.permissions import admin_required
from accounts.roles import player_for, role_of
from league.models import Player
from ui.nav import nav_for

pytestmark = pytest.mark.django_db


def labels(links):
    return [link.label for link in links]


@pytest.fixture
def org():
    return Organization.objects.create(name="Waco Regional")


def make_user(org, email, is_admin=False):
    return User.objects.create_user(email, "pw", organization=org, is_admin=is_admin)


def test_role_admin(org):
    assert role_of(make_user(org, "a@example.com", is_admin=True)) == "admin"


def test_role_admin_player_by_email_any_case(org):
    Player.objects.create(organization=org, name="Ann", email="Ann@Example.com")
    user = make_user(org, "ann@example.com", is_admin=True)
    assert role_of(user) == "admin_player"
    assert player_for(user).name == "Ann"


def test_role_plain_user_is_player(org):
    assert role_of(make_user(org, "p@example.com")) == "player"


def test_player_in_other_org_does_not_count(org):
    other = Organization.objects.create(name="Elsewhere")
    Player.objects.create(organization=other, name="Ann", email="ann@example.com")
    assert player_for(make_user(org, "ann@example.com", is_admin=True)) is None


def test_user_without_org_has_no_player():
    assert player_for(User.objects.create_user("x@example.com", "pw")) is None


def test_linked_player_wins(org):
    user = make_user(org, "p@example.com")
    Player.objects.create(organization=org, name="Linked", user=user)
    assert player_for(user).name == "Linked"


@pytest.mark.urls("tests.future_urls")
def test_admin_nav(org):
    nav = nav_for(make_user(org, "a@example.com", is_admin=True), None)
    assert labels(nav.top) == ["My Events", "Players", "Admins"]
    assert labels(nav.tabs) == ["Events", "Tonight", "Players"]
    assert labels(nav.more) == ["Admins", "Account"]
    assert nav.account.label == "Account"


@pytest.mark.urls("tests.future_urls")
def test_admin_player_nav(org):
    Player.objects.create(organization=org, name="Ann", email="ann@example.com")
    nav = nav_for(make_user(org, "ann@example.com", is_admin=True), None)
    assert labels(nav.top) == ["My Events", "My Games", "Players", "Admins"]
    assert labels(nav.tabs) == ["Events", "Tonight", "My Games"]
    assert labels(nav.more) == ["Players", "Admins", "Account"]


@pytest.mark.urls("tests.future_urls")
def test_player_nav(org):
    nav = nav_for(make_user(org, "p@example.com"), None)
    assert labels(nav.top) == ["My Games"]
    assert labels(nav.tabs) == ["My Games", "Standings", "Account"]
    assert nav.more == []


@pytest.mark.urls("tests.nav_urls_partial")
def test_unbuilt_pages_are_hidden(org):
    nav = nav_for(make_user(org, "a@example.com", is_admin=True), None)
    assert labels(nav.top) == ["My Events"]
    assert labels(nav.tabs) == ["Events"]
    assert labels(nav.more) == ["Account"]


@pytest.mark.urls("tests.future_urls")
def test_active_item(org):
    nav = nav_for(make_user(org, "a@example.com", is_admin=True), "event_list")
    assert [link.active for link in nav.tabs] == [True, False, False]


def test_context_processor_anonymous():
    from ui.context_processors import nav

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    assert nav(request) == {"nav": None}


def test_admin_required(org):
    view = admin_required(lambda request: HttpResponse("ok"))
    request = RequestFactory().get("/events/")
    request.user = AnonymousUser()
    assert view(request).status_code == 302
    request.user = make_user(org, "p@example.com")
    with pytest.raises(PermissionDenied):
        view(request)
    request.user = make_user(org, "a@example.com", is_admin=True)
    assert view(request).content == b"ok"
