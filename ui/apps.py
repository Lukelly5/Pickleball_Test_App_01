from django.apps import AppConfig


class UiConfig(AppConfig):
    name = "ui"
    verbose_name = "Stryde UI"

    def ready(self):
        from django.contrib import admin

        admin.site.site_header = "Stryde"
        admin.site.site_title = "Stryde admin"
