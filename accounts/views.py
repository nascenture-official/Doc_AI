from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.urls import reverse
from allauth.account.models import EmailAddress
from allauth.account.internal.flows.email_verification import send_verification_email_to_address
from .forms import ProfileUpdateForm
from .models import UserProfile

class ResendVerificationEmailView(View):
    """Handles the /accounts/confirm-email/ page for link-based email verification.

    GET  → show the verification_sent template.
    POST → resend the verification email using the pending email stored in the session.
    """

    template_name = "account/verification_sent.html"

    def get(self, request):
        email = request.session.get("pending_verification_email")
        email_verified = False
        if email:
            email_verified = EmailAddress.objects.filter(
                email__iexact=email, verified=True
            ).exists()
        return render(request, self.template_name, {
            "email_verified": email_verified,
            "pending_email": email,
        })

    def post(self, request):
        email = request.session.get("pending_verification_email")
        if email:
            try:
                address = EmailAddress.objects.get(email__iexact=email, verified=False)
                send_verification_email_to_address(request, address)
                messages.success(request, f"Verification email resent to {email}.")
            except EmailAddress.DoesNotExist:
                messages.error(request, "Could not find an unverified email address. Please sign up again.")
        else:
            messages.error(request, "Session expired. Please sign up again.")
        return redirect(reverse("account_email_verification_sent"))


class DashboardView(LoginRequiredMixin, View):
    """Main dashboard shown after login."""

    login_url = "/accounts/login/"

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        context = {
            "profile": profile,
            "page_title": "Dashboard",
        }
        return render(request, "accounts/dashboard.html", context)


class ProfileView(LoginRequiredMixin, View):
    """User profile update page."""

    login_url = "/accounts/login/"

    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = ProfileUpdateForm(instance=profile, user=request.user)
        context = {
            "form": form,
            "profile": profile,
            "page_title": "Edit Profile",
        }
        return render(request, "accounts/profile.html", context)

    def post(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=profile,
            user=request.user,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully! 🎉")
            return redirect("profile")
        context = {
            "form": form,
            "profile": profile,
            "page_title": "Edit Profile",
        }
        return render(request, "accounts/profile.html", context)
