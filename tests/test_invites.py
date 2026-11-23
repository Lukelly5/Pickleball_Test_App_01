from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.invites import ALREADY_USED, InviteError, accept_invite
from accounts.models import Organization, User
from league.models import Invite, Player

pytestmark = pytest.mark.django_db
PW = {"new_password1": "n3w-Str0ng-pw", "new_password2": "n3w-Str0ng-pw"}


@pytest.fixture
def org():
    return Organization.objects.create(name="Waco Regional")


@pytest.fixture
def player_invite(org):
    player = Player.objects.create(organization=org, name="Pat Lee", email="pat@example.com")
    return Invite.objects.create(
        organization=org, email="pat@example.com", role="player", player=player
    )


def test_invite_page_shows_email_and_form(client, player_invite):
    html = client.get(f"/invite/{player_invite.token}/").content.decode()
    assert "pat@example.com" in html and 'name="new_password1"' in html


def test_accept_player_invite(client, player_invite):
    response = client.post(f"/invite/{player_invite.token}/", PW, follow=True)
    assert response.redirect_chain[-1][0] == "/me/"
    assert "Welcome to Stryde." in response.content.decode()
    user = User.objects.get(email="pat@example.com")
    assert user.organization == player_invite.organization and not user.is_admin
    assert Player.objects.get(name="Pat Lee").user == user
    player_invite.refresh_from_db()
    assert player_invite.accepted_at is not None


def test_accept_admin_invite_links_matching_player(client, org):
    Player.objects.create(organization=org, name="Ann", email="Ann@Example.com")
    invite = Invite.objects.create(organization=org, email="ann@example.com", role="admin")
    client.post(f"/invite/{invite.token}/", PW)
    user = User.objects.get(email="ann@example.com")
    assert user.is_admin and user.player.name == "Ann"
    assert client.get("/").url == "/events/"


def test_expired_invite(client, player_invite):
    player_invite.expires_at = timezone.now() - timedelta(minutes=1)
    player_invite.save()
    html = client.get(f"/invite/{player_invite.token}/").content.decode()
    assert "This invite link has expired. Ask your league admin to resend it." in html
    assert 'name="new_password1"' not in html


def test_unknown_token_404(client):
    assert client.get("/invite/not-a-token/").status_code == 404


def test_email_already_has_account_any_case(client, player_invite):
    User.objects.create_user("PAT@example.com", "pw")
    html = client.get(f"/invite/{player_invite.token}/").content.decode()
    assert "That email already has an account" in html
    assert 'name="new_password1"' not in html


def test_weak_password_rejected(client, player_invite):
    response = client.post(
        f"/invite/{player_invite.token}/",
        {"new_password1": "password", "new_password2": "password"},
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="pat@example.com").exists()


def test_accepting_twice_makes_one_user(client, player_invite):
    accept_invite(player_invite.token, "n3w-Str0ng-pw")
    with pytest.raises(InviteError, match=ALREADY_USED):
        accept_invite(player_invite.token, "n3w-Str0ng-pw")
    assert User.objects.filter(email__iexact="pat@example.com").count() == 1
    assert ALREADY_USED in client.post(f"/invite/{player_invite.token}/", PW).content.decode()


def test_player_linked_to_someone_else_is_not_taken(org, player_invite):
    other = User.objects.create_user("other@example.com", "pw", organization=org)
    player_invite.player.user = other
    player_invite.player.save()
    user = accept_invite(player_invite.token, "n3w-Str0ng-pw")
    assert Player.objects.get(name="Pat Lee").user == other
    assert not Player.objects.filter(user=user).exists()
