from .nav import nav_for


def nav(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"nav": None}
    match = getattr(request, "resolver_match", None)
    return {"nav": nav_for(user, match.url_name if match else None)}
