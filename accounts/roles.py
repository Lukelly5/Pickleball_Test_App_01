"""Who a logged-in user is to Stryde (PRD §2): admin, player, or an admin who also plays."""
from typing import Literal

from league.models import Player

Role = Literal["admin", "admin_player", "player"]
_UNSET = object()


def player_for(user) -> Player | None:
    """The user's Player: the linked one, else one in their organization with the same email."""
    if not getattr(user, "is_authenticated", False):
        return None
    cached = getattr(user, "_stryde_player", _UNSET)
    if cached is not _UNSET:
        return cached
    player = Player.objects.filter(user=user).first()
    if player is None and user.organization_id and user.email:
        player = (
            Player.objects.filter(organization_id=user.organization_id, email__iexact=user.email)
            .order_by("pk")
            .first()
        )
    user._stryde_player = player
    return player


def role_of(user) -> Role:
    if user.is_admin:
        return "admin_player" if player_for(user) else "admin"
    return "player"
