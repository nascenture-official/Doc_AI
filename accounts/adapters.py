from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class CustomAccountAdapter(DefaultAccountAdapter):
    """Extend allauth's adapter to persist first_name and last_name."""

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """Store the pending email in the session so verification_sent.html can display it."""
        request.session["pending_verification_email"] = emailconfirmation.email_address.email
        return super().send_confirmation_mail(request, emailconfirmation, signup)

    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        user.first_name = form.cleaned_data.get("first_name", "")
        user.last_name = form.cleaned_data.get("last_name", "")
        if commit:
            user.save()
        return user


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Populate first/last name from social login provider data."""

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not user.first_name:
            user.first_name = (
                data.get("first_name")
                or data.get("given_name")
                or (data.get("name") or "").split(" ", 1)[0]
                or ""
            )
        if not user.last_name:
            user.last_name = (
                data.get("last_name")
                or data.get("family_name")
                or (data.get("name") or "").split(" ", 1)[1]
                if " " in (data.get("name") or "")
                else ""
            )
        return user
