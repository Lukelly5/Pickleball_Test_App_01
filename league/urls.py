from django.urls import path

from . import event_views, preview_views, setup_views, views

urlpatterns = [
    path("events/", views.event_list, name="event_list"),
    path("events/new/", setup_views.event_create, name="event_create"),
    path("events/<int:pk>/setup/", setup_views.event_setup, name="event_setup"),
    path("events/<int:pk>/setup/games/preview/", setup_views.event_games_preview, name="event_games_preview"),
    path("events/<int:pk>/setup/games/generate/", setup_views.event_generate, name="event_generate"),
    path("events/<int:pk>/setup/teams/row/", setup_views.event_team_row, name="event_team_row"),
    path("events/<int:pk>/setup/teams/players/", setup_views.player_search, name="player_search"),
    path(
        "events/<int:pk>/setup/teams/<int:team_pk>/delete/",
        setup_views.event_team_delete,
        name="event_team_delete",
    ),
    path("events/<int:pk>/setup/<str:step>/", setup_views.event_setup_step, name="event_setup_step"),
    path("events/<int:pk>/preview/", preview_views.event_preview, name="event_preview"),
    path("events/<int:pk>/preview/edit/", preview_views.event_preview_edit, name="event_preview_edit"),
    path("events/<int:pk>/preview/regenerate/", preview_views.event_preview_regenerate, name="event_preview_regenerate"),
    path("events/<int:pk>/preview/publish/", preview_views.event_preview_publish, name="event_preview_publish"),
    path("events/<int:pk>/schedule/", event_views.event_schedule, name="event_schedule"),
    path("events/<int:pk>/standings/", event_views.event_standings, name="event_standings"),
    path("events/<int:pk>/teams/", event_views.event_teams, name="event_teams"),
    path("events/<int:pk>/settings/", event_views.event_settings, name="event_settings"),
    path("events/<int:pk>/settings/share/reset/", event_views.event_share_reset, name="event_share_reset"),
    path("s/<str:token>/schedule/", event_views.share_schedule, name="share_schedule"),
    path("s/<str:token>/standings/", event_views.share_standings, name="share_standings"),
    path("s/<str:token>/teams/", event_views.share_teams, name="share_teams"),
    path("tonight/", event_views.tonight, name="tonight"),
    path("me/", views.my_games, name="my_games"),
]
