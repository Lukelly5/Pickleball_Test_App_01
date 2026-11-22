from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def admin_required(view):
    """League Admins only. Anonymous users go to log in; other users get a 403."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(wrapped)
