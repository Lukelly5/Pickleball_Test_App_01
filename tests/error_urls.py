"""The real URLconf plus views that fail, for the 403 and 500 pages."""
from django.core.exceptions import PermissionDenied
from django.urls import path

from config import urls as real


def boom(request):
    raise RuntimeError("boom")


def forbidden(request):
    raise PermissionDenied


urlpatterns = list(real.urlpatterns) + [
    path("boom/", boom),
    path("forbidden/", forbidden),
]
