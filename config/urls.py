"""URL configuration for the Pickleball League Manager."""
from django.contrib import admin
from django.urls import path

admin.site.site_header = "Pickleball League Manager"

urlpatterns = [
    path("admin/", admin.site.urls),
]
