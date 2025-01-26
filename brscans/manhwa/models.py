from django.conf import settings
from django.db import models


class ImageVariants(models.Model):
    minimum = models.ImageField(null=True)
    medium = models.ImageField(null=True)
    original = models.ImageField(null=True)
    translated = models.ImageField(null=True)

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
    external_id = models.SlugField(max_length=64, db_index=True, null=True)
    slug = models.SlugField(max_length=64, db_index=True, null=True)
    hash_external_id = models.CharField(max_length=64, unique=True, null=True)
    hash_slug = models.CharField(max_length=64, unique=True, null=True)
    thumbnail = models.ForeignKey(
        ImageVariants, on_delete=models.CASCADE, blank=True, null=True
    )

    source = models.URLField(null=True, blank=True)
    identifier = models.CharField(max_length=255, null=True, unique=True)

    genres = models.ManyToManyField(Genre, related_name="manhwas")

    def __str__(self):
        return self.title


class Chapter(models.Model):
    identifier = models.CharField(max_length=255, null=True, unique=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, db_index=True)
    release_date = models.DateTimeField(null=True)
    manhwa = models.ForeignKey(
        Manhwa, on_delete=models.CASCADE, related_name="chapters", null=True
    )
    quantity_pages = models.IntegerField(null=True)

    source = models.URLField(null=True, blank=True)


class Page(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="pages")
    images = models.OneToOneField(ImageVariants, on_delete=models.CASCADE, null=True)
    quantity_merged = models.IntegerField(null=True)
