from django.urls import path

from . import setup_views, views

urlpatterns = [
    path("events/", views.event_list, name="event_list"),
    path("events/new/", setup_views.event_create, name="event_create"),
    path("events/<int:pk>/setup/", setup_views.event_setup, name="event_setup"),
    path("events/<int:pk>/setup/<str:step>/", setup_views.event_setup_step, name="event_setup_step"),
    path("me/", views.my_games, name="my_games"),
]
