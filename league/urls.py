from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.event_list, name="event_list"),
    path("me/", views.my_games, name="my_games"),
]
