"""URL configuration for core project."""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect


def root_redirect(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("account_login")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),      # Custom views (must come first)
    path("accounts/", include("allauth.urls")),       # All allauth routes
    path("", root_redirect, name="root"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
