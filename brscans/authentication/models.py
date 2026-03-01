from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    avatar = models.URLField(blank=True, null=True)
    bio = models.TextField(blank=True, default="")
    discord_id = models.CharField(
        max_length=64, unique=True, null=True, blank=True
    )
    discord_username = models.CharField(max_length=128, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username


class Favorite(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    manhwa = models.ForeignKey(
        "manhwa.Manhwa", on_delete=models.CASCADE, related_name="favorites"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "manhwa")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} -> {self.manhwa.title}"
