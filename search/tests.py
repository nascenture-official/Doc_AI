from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.urls import reverse


class SearchViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="searcher", email="searcher@example.com", password="testpass"
        )
        self.client.login(username="searcher", password="testpass")

    def test_search_view_get_empty_query(self):
        """Search page loads with no query string."""
        response = self.client.get(reverse("search:search"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search Documents")

    def test_search_view_requires_login(self):
        """Unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.get(reverse("search:search"))
        self.assertRedirects(response, "/accounts/login/?next=/search/")
