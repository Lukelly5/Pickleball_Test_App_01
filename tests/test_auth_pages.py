import pytest
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.models import Organization, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def org():
    return Organization.objects.create(name="Waco Regional")


def test_login_page(client):
    html = client.get("/login/").content.decode()
    assert "Log in" in html and 'href="/password-reset/"' in html and "data-nav" not in html


def test_home_anonymous_goes_to_login(client):
    assert client.get("/").url == "/login/"


def test_admin_lands_on_events(client, org):
    User.objects.create_user("a@example.com", "pw-Str0ng-1", organization=org, is_admin=True)
    response = client.post(
        "/login/", {"username": "a@example.com", "password": "pw-Str0ng-1"}, follow=True
    )
    assert response.redirect_chain[-1][0] == "/events/"


def test_player_lands_on_my_games(client, org):
    User.objects.create_user("p@example.com", "pw-Str0ng-1", organization=org)
    response = client.post(
        "/login/", {"username": "p@example.com", "password": "pw-Str0ng-1"}, follow=True
    )
    assert response.redirect_chain[-1][0] == "/me/"


def test_login_ignores_email_case(client, org):
    User.objects.create_user("pat@example.com", "pw-Str0ng-1", organization=org)
    client.post("/login/", {"username": "PAT@Example.com", "password": "pw-Str0ng-1"})
    assert client.get("/").url == "/me/"


def test_wrong_password(client, org):
    User.objects.create_user("p@example.com", "pw-Str0ng-1", organization=org)
    response = client.post("/login/", {"username": "p@example.com", "password": "nope"})
    assert response.status_code == 200
    assert "correct email" in response.content.decode().lower()


def test_logged_in_user_skips_login(client, org):
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=org))
    assert client.get("/login/").status_code == 302


def test_logout(client, org):
    client.force_login(User.objects.create_user("p@example.com", "pw", organization=org))
    assert client.get("/logout/").status_code == 405
    response = client.post("/logout/", follow=True)
    assert response.redirect_chain[-1][0] == "/login/"
    html = response.content.decode()
    assert "You&#x27;re logged out." in html or "You're logged out." in html


def test_password_reset_email(client, org, mailoutbox):
    User.objects.create_user("p@example.com", "pw", organization=org)
    response = client.post("/password-reset/", {"email": "p@example.com"})
    assert response.url == "/password-reset/sent/"
    assert len(mailoutbox) == 1
    assert mailoutbox[0].subject == "Reset your Stryde password"
    assert "/reset/" in mailoutbox[0].body


def test_password_reset_unknown_email_looks_the_same(client, mailoutbox):
    response = client.post("/password-reset/", {"email": "nobody@example.com"})
    assert response.url == "/password-reset/sent/" and mailoutbox == []


def test_password_reset_confirm_sets_password(client, org):
    user = User.objects.create_user("p@example.com", "old", organization=org)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    response = client.get(f"/reset/{uid}/{default_token_generator.make_token(user)}/", follow=True)
    set_url = response.redirect_chain[-1][0]
    client.post(set_url, {"new_password1": "n3w-Str0ng-pw", "new_password2": "n3w-Str0ng-pw"})
    user.refresh_from_db()
    assert user.check_password("n3w-Str0ng-pw")


def test_password_reset_bad_link(client):
    html = client.get("/reset/MQ/bad-token/", follow=True).content.decode()
    assert "This reset link has expired or was already used." in html


def test_account_changes_password(client, org):
    user = User.objects.create_user("p@example.com", "old-Str0ng-1", organization=org)
    client.force_login(user)
    assert 'action="/logout/"' in client.get("/account/").content.decode()
    response = client.post(
        "/account/",
        {"old_password": "old-Str0ng-1", "new_password1": "n3w-Str0ng-pw",
         "new_password2": "n3w-Str0ng-pw"},
        follow=True,
    )
    assert "Your password was changed." in response.content.decode()


def test_form_inputs_sit_in_basecoat_field(client):
    # Basecoat 1.1 styles only inputs that are direct children of .field; a bare input renders with no border.
    html = client.get("/login/").content.decode()
    assert '<div class="field' in html
    assert html.count('<div class="field') == 2  # email and password
