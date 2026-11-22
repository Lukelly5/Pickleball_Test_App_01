"""Accepting an invite link (PRD Flow D): set a password, get an account, link the player."""
from django.db import transaction
from django.utils import timezone

from league.models import Invite, Player

from .models import User

ALREADY_USED = "This invite has already been used. Log in instead."
EXPIRED = "This invite link has expired. Ask your league admin to resend it."
HAS_ACCOUNT = "That email already has an account — log in instead."


class InviteError(Exception):
    """The invite can't be accepted; the message is shown to the person."""


def check_invite(invite: Invite) -> None:
    if invite.accepted_at is not None:
        raise InviteError(ALREADY_USED)
    if invite.is_expired():
        raise InviteError(EXPIRED)
    if User.objects.filter(email__iexact=invite.email).exists():
        raise InviteError(HAS_ACCOUNT)


def _player_to_link(invite: Invite) -> Player | None:
    if invite.player_id and invite.player.user_id is None:
        return invite.player
    return (
        Player.objects.filter(
            organization_id=invite.organization_id,
            email__iexact=invite.email,
            user__isnull=True,
        )
        .order_by("pk")
        .first()
    )


def accept_invite(token: str, password: str) -> User:
    """Create the invited person's account. Raises Invite.DoesNotExist or InviteError."""
    with transaction.atomic():
        invite = Invite.objects.select_for_update().select_related("player").get(token=token)
        check_invite(invite)
        user = User.objects.create_user(
            invite.email,
            password,
            organization_id=invite.organization_id,
            is_admin=invite.role == Invite.Role.ADMIN,
        )
        player = _player_to_link(invite)
        if player is not None:
            player.user = user
            player.save(update_fields=["user"])
        invite.accepted_at = timezone.now()
        invite.save(update_fields=["accepted_at"])
    return user
