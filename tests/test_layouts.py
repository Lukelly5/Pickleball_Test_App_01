import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template import engines
from django.test import Client, RequestFactory
from django.urls import resolve

from accounts.models import Organization, User

pytestmark = pytest.mark.django_db
APP_PAGE = (
    '{% extends "base_app.html" %}{% block page_title %}My Events{% endblock %}'
    "{% block content %}hello{% endblock %}"
)
PUBLIC_PAGE = '{% extends "base_public.html" %}{% block content %}hello{% endblock %}'


def render(source, user=None, path="/events/", **context):
    request = RequestFactory().get(path)
    request.user = user or AnonymousUser()
    return engines["django"].from_string(source).render(context, request)


@pytest.fixture
def admin_user():
    org = Organization.objects.create(name="Waco Regional")
    return User.objects.create_user("a@example.com", "pw", organization=org, is_admin=True)


@pytest.mark.urls("tests.future_urls")
def test_app_frame_has_top_bar_and_tab_bar(admin_user):
    html = render(APP_PAGE, admin_user)
    assert 'data-nav="top"' in html and 'data-nav="tabs"' in html and 'data-nav="more"' in html
    assert "hidden md:flex" in html and "md:hidden" in html
    assert "My Events" in html and "Tonight" in html and "hello" in html
    assert 'action="/logout/"' in html and 'method="post"' in html


@pytest.mark.urls("tests.future_urls")
def test_player_frame_has_no_more_tab():
    user = User.objects.create_user("p@example.com", "pw")
    html = render(APP_PAGE, user)
    assert 'data-nav="tabs"' in html and 'data-nav="more"' not in html
    assert "Standings" in html


@pytest.mark.urls("tests.future_urls")
def test_active_tab_marked(admin_user):
    request = RequestFactory().get("/events/")
    request.resolver_match = resolve("/events/")
    request.user = admin_user
    html = engines["django"].from_string(APP_PAGE).render({}, request)
    assert 'aria-current="page"' in html


def test_public_frame_has_no_navigation():
    html = render(PUBLIC_PAGE)
    assert "data-nav" not in html and "stryde-monogram.svg" in html and "hello" in html


def test_messages_render_as_toasts():
    html = render(PUBLIC_PAGE, messages=[Message(constants.SUCCESS, "Saved.")])
    toaster = html.split('id="toaster"', 1)[1]
    assert "Saved." in toaster and 'data-category="success"' in toaster


def test_404_page():
    response = Client().get("/no-such-page/")
    assert response.status_code == 404
    assert "We couldn't find that page." in response.content.decode()


@pytest.mark.urls("tests.error_urls")
def test_403_page():
    response = Client().get("/forbidden/")
    assert response.status_code == 403
    assert "have access to this page." in response.content.decode()


@pytest.mark.urls("tests.error_urls")
def test_500_page():
    response = Client(raise_request_exception=False).get("/boom/")
    assert response.status_code == 500
    assert "Something went wrong loading this page. Refresh to try again." in response.content.decode()
