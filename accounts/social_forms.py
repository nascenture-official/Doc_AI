from django import forms
from allauth.socialaccount.forms import SignupForm as SocialSignupForm


class CustomSocialSignupForm(SocialSignupForm):
    agree_terms = forms.BooleanField(
        required=True,
        error_messages={
            "required": "You must agree to the Terms of Service and Privacy Policy to register."
        }
    )
