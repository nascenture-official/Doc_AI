from unittest.mock import MagicMock
from django.test import TestCase
from accounts.forms import CustomSignupForm
from accounts.social_forms import CustomSocialSignupForm


class CustomSignupFormTests(TestCase):
    def test_signup_form_validation_fails_without_agree_terms(self):
        data = {
            "first_name": "Test",
            "last_name": "User",
            "agree_terms": False,
        }
        form = CustomSignupForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("agree_terms", form.errors)
        self.assertEqual(
            form.errors["agree_terms"],
            ["You must agree to the Terms of Service and Privacy Policy to register."]
        )

    def test_signup_form_validation_succeeds_with_agree_terms(self):
        data = {
            "first_name": "Test",
            "last_name": "User",
            "agree_terms": True,
        }
        form = CustomSignupForm(data=data)
        self.assertTrue(form.is_valid())


class CustomSocialSignupFormTests(TestCase):
    def test_social_signup_form_validation_fails_without_agree_terms(self):
        data = {
            "agree_terms": False,
        }
        form = CustomSocialSignupForm(data=data, sociallogin=MagicMock())
        self.assertFalse(form.is_valid())
        self.assertIn("agree_terms", form.errors)
        self.assertEqual(
            form.errors["agree_terms"],
            ["You must agree to the Terms of Service and Privacy Policy to register."]
        )

    def test_social_signup_form_validation_succeeds_with_agree_terms(self):
        data = {
            "agree_terms": True,
        }
        form = CustomSocialSignupForm(data=data, sociallogin=MagicMock())
        form.is_valid()
        self.assertNotIn("agree_terms", form.errors)
