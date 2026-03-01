from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class ImageVariants(models.Model):
    minimum = models.ImageField(null=True)
    medium = models.ImageField(null=True)
    original = models.ImageField(null=True)
    translated = models.ImageField(null=True)
    raw = models.ImageField(null=True)
    upscaled = models.ImageField(null=True)

    def save(self, *args, **kwargs):
        if self.translated and self.translated.name.startswith(
            settings.PUBLIC_MEDIA_LOCATION
        ):
            self.translated.name = self.translated.name.replace(
                settings.PUBLIC_MEDIA_LOCATION, ""
            )
        super().save(*args, **kwargs)


class Genre(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=40)

    def __str__(self):
        return self.name


class Manhwa(models.Model):
    title = models.CharField(max_length=100)
    author = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=100)
    description = models.TextField()
    external_id = models.CharField(max_length=64, db_index=True, null=True)
    slug = models.SlugField(max_length=64, db_index=True, null=True)
    hash_external_id = models.CharField(max_length=64, unique=True, null=True)
    hash_slug = models.CharField(max_length=64, unique=True, null=True)
    thumbnail = models.ForeignKey(
        ImageVariants, on_delete=models.CASCADE, blank=True, null=True
    )

    source = models.URLField(null=True, blank=True)
    identifier = models.CharField(max_length=255, null=True, unique=True)

    is_nsfw = models.BooleanField(default=False)

    genres = models.ManyToManyField(Genre, related_name="manhwas", blank=True)

    def __str__(self):
        return self.title


class Chapter(models.Model):
    identifier = models.CharField(max_length=255, null=True, unique=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    release_date = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    manhwa = models.ForeignKey(
        Manhwa, on_delete=models.CASCADE, related_name="chapters", null=True
    )
    quantity_pages = models.IntegerField(null=True)

    source = models.URLField(null=True, blank=True)


class Page(models.Model):
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="pages"
    )
    images = models.OneToOneField(
        ImageVariants, on_delete=models.CASCADE, null=True
    )
    order = models.PositiveIntegerField(default=0)
    quantity_merged = models.IntegerField(null=True)

    class Meta:
        ordering = ["order"]


class ReadingHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reading_history",
    )
    manhwa = models.ForeignKey(
        Manhwa, on_delete=models.CASCADE, related_name="reading_history"
    )
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="reading_history"
    )
    page_number = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "manhwa")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user} - {self.manhwa} (Cap. {self.chapter.title}, Pág. {self.page_number})"


class ReadChapter(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="read_chapters",
    )
    manhwa = models.ForeignKey(
        Manhwa, on_delete=models.CASCADE, related_name="read_chapters"
    )
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="read_chapters"
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "chapter")
        ordering = ["-read_at"]

    def __str__(self):
        return f"{self.user} leu {self.chapter.title} ({self.manhwa.title})"


class Comment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    chapter = models.ForeignKey(
        Chapter, on_delete=models.CASCADE, related_name="comments"
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} em {self.chapter}: {self.content[:20]}"


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ("new_chapter", "Novo Capítulo"),
        ("system", "Sistema"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(
        max_length=20, choices=NOTIFICATION_TYPES, default="new_chapter"
    )
    manhwa = models.ForeignKey(
        Manhwa,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    chapter = models.ForeignKey(
        Chapter,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notificação para {self.user}: {self.type} - Lido: {self.read}"


@receiver(post_save, sender=Chapter)
def create_chapter_notification(sender, instance, created, **kwargs):
    if created and instance.manhwa:
        from brscans.authentication.models import Favorite

        favorites = Favorite.objects.filter(
            manhwa=instance.manhwa
        ).select_related("user")
        notifications = []
        for fav in favorites:
            notifications.append(
                Notification(
                    user=fav.user,
                    type="new_chapter",
                    manhwa=instance.manhwa,
                    chapter=instance,
                )
            )
        if notifications:
            Notification.objects.bulk_create(notifications)
