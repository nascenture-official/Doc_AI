from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
    path("profile/remove-avatar/", views.RemoveAvatarView.as_view(), name="remove_avatar"),
    path("confirm-email/", views.ResendVerificationEmailView.as_view(), name="account_email_verification_sent"),
    path("email/", RedirectView.as_view(pattern_name="profile", permanent=False), name="account_email"),
]
