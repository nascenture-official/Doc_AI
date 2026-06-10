from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    bio = models.TextField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return "/static/img/default_avatar.svg"

    def get_initials(self):
        """Return up to 2 initials — fallback when no avatar is set."""
        name = self.user.get_full_name() or self.user.username
        parts = name.split()
        return "".join(p[0].upper() for p in parts[:2])
