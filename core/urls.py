"""URL configuration for core project."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import landing_page


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),      # Custom views (must come first)
    path("accounts/", include("allauth.urls")),       # All allauth routes
    path("documents/", include("documents.urls")),
    path("chat/", include("chat.urls")),
    path("search/", include("search.urls")),
    path("teams/", include("teams.urls")),
    path("", landing_page, name="root"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
