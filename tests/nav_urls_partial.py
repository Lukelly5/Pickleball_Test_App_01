"""Only two of the nav's pages exist: the rest must be hidden."""
from django.http import HttpResponse
from django.urls import path


def stand_in(request):
    return HttpResponse("stand-in")


urlpatterns = [
    path("events/", stand_in, name="event_list"),
    path("account/", stand_in, name="account"),
]
