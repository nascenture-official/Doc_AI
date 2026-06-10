from django import forms
from .models import UserProfile


class CustomSignupForm(forms.Form):
    """
    Extra fields added to the allauth signup form.
    Must only declare EXTRA fields — allauth handles email/username/password.
    Registered via ACCOUNT_SIGNUP_FORM_CLASS in settings.
    """

    first_name = forms.CharField(
        max_length=30,
        label="First name",
        widget=forms.TextInput(attrs={"placeholder": "First name", "class": "form-control"}),
    )
    last_name = forms.CharField(
        max_length=30,
        label="Last name",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Last name (optional)", "class": "form-control"}),
    )

    def signup(self, request, user):
        """Called by allauth after user is saved — persist extra fields."""
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.save()


class ProfileUpdateForm(forms.ModelForm):
    """Form to edit user's name, bio and avatar."""

    first_name = forms.CharField(
        max_length=30,
        required=False,
        label="First name",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        label="Last name",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
    )

    class Meta:
        model = UserProfile
        fields = ["avatar", "bio"]
        widgets = {
            "bio": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Tell us a bit about yourself…",
                }
            ),
            "avatar": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "image/*", "id": "id_avatar"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields["first_name"].initial = self.user.first_name
            self.fields["last_name"].initial = self.user.last_name

    def save(self, commit=True):
        profile = super().save(commit=False)
        if self.user:
            self.user.first_name = self.cleaned_data.get("first_name", "")
            self.user.last_name = self.cleaned_data.get("last_name", "")
            self.user.save()
        if commit:
            profile.save()
        return profile
