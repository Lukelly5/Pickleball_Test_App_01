import pytest
from django.db import IntegrityError

from accounts.models import Organization, User

pytestmark = pytest.mark.django_db


def test_create_user_logs_in_by_email():
    user = User.objects.create_user("Pat@Example.com", "pw12345!")
    assert user.email == "Pat@example.com"          # domain normalised
    assert user.check_password("pw12345!")
    assert not user.is_admin and not user.is_staff
    assert not hasattr(user, "username") or user.username is None


def test_create_user_requires_email():
    with pytest.raises(ValueError):
        User.objects.create_user("", "pw")


def test_create_superuser_is_staff_superuser_and_league_admin():
    user = User.objects.create_superuser("admin@example.com", "pw12345!")
    assert user.is_staff and user.is_superuser and user.is_admin


def test_email_is_unique():
    User.objects.create_user("a@example.com", "pw")
    with pytest.raises(IntegrityError):
        User.objects.create_user("a@example.com", "pw")


def test_user_belongs_to_organization():
    org = Organization.objects.create(name="Waco Regional")
    user = User.objects.create_user("a@example.com", "pw", organization=org)
    assert list(org.users.all()) == [user]


def test_admin_login_page_loads(client):
    assert client.get("/admin/login/").status_code == 200


def test_admin_add_user_page_loads(admin_client):
    assert admin_client.get("/admin/accounts/user/add/").status_code == 200


def test_admin_add_user_form_creates_user(admin_client):
    response = admin_client.post(
        "/admin/accounts/user/add/",
        {
            "email": "new@example.com",
            "usable_password": "true",
            "password1": "pw-Str0ng-12345",
            "password2": "pw-Str0ng-12345",
        },
    )
    assert response.status_code == 302
    assert User.objects.get(email="new@example.com").check_password("pw-Str0ng-12345")
